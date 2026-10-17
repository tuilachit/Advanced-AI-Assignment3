from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.domain.models import (
    FactInput,
    FactStatus,
    ResumeEntry,
    ResumeEntryDetail,
    ResumeEntryEdit,
    ResumeEntryKind,
    ResumeEntryStatus,
    ResumeEntryValidationIssue,
    ResumeText,
    SessionState,
    ValidationSeverity,
)
from app.domain.workflow import InvalidTransitionError, SessionWorkflow
from app.providers.base import ProviderProtocolError, ProviderUnavailableError

REQUIRED_FACTS = [
    FactInput(field="name", value="Maya Chen"),
    FactInput(field="education", value="Bachelor of Computing Science at UTS"),
    FactInput(field="skills", value="Python, SQL, REST APIs"),
    FactInput(field="project", value="Built a course-planning API with Python"),
    FactInput(field="target_role", value="Software Engineering Intern"),
]


def proposed_entry(fact_id: str) -> ResumeEntry:
    return ResumeEntry(
        kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="Course-planning API", fact_ids=[fact_id]),
        organisation_or_context=ResumeText(text="UTS coursework", fact_ids=[fact_id]),
        details=[
            ResumeEntryDetail(
                label="Technologies",
                value=ResumeText(text="Python", fact_ids=[fact_id]),
            )
        ],
        bullets=[ResumeText(text="Built a course-planning API with Python.", fact_ids=[fact_id])],
        source_fact_ids=[fact_id],
    )


def confirmed_workflow() -> tuple[SessionWorkflow, str, str]:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    workflow.update_profile(session.session_id, REQUIRED_FACTS, source_reference="message-1")
    workflow.confirm_profile(session.session_id)
    project_fact_id = next(
        fact.fact_id for fact in session.profile.facts if fact.field == "project"
    )
    return workflow, session.session_id, project_fact_id


def test_resume_entry_requires_per_item_fact_provenance_and_exact_source_union() -> None:
    entry = ResumeEntry(
        kind=ResumeEntryKind.EXPERIENCE,
        heading=ResumeText(text="Data Science Intern", fact_ids=["fact-experience"]),
        bullets=[
            ResumeText(text="Investigated AI-chatbot failures.", fact_ids=["fact-experience"])
        ],
        source_fact_ids=["fact-experience"],
    )

    assert entry.status is ResumeEntryStatus.PROPOSED

    with pytest.raises(ValidationError, match="source_fact_ids"):
        ResumeEntry(
            kind=ResumeEntryKind.EXPERIENCE,
            heading=ResumeText(text="Data Science Intern", fact_ids=["fact-heading"]),
            bullets=[ResumeText(text="Investigated failures.", fact_ids=["fact-bullet"])],
            source_fact_ids=["fact-heading"],
        )

    with pytest.raises(ValidationError, match="must not be blank"):
        ResumeText(text="   ", fact_ids=["fact-experience"])


def test_set_entries_requires_confirmed_profile_and_resets_entries_to_proposed() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    entry = proposed_entry("fact-project")

    with pytest.raises(InvalidTransitionError, match="Confirm the profile"):
        workflow.set_resume_entries(session.session_id, [entry])

    workflow.update_profile(session.session_id, REQUIRED_FACTS, source_reference="message-1")
    workflow.confirm_profile(session.session_id)
    entry = proposed_entry(
        next(fact.fact_id for fact in session.profile.facts if fact.field == "project")
    )
    entry.status = ResumeEntryStatus.APPROVED

    stored = workflow.set_resume_entries(session.session_id, [entry])

    assert stored.state is SessionState.RESUME_ENTRIES_REVIEW
    assert stored.resume_entries[0].status is ResumeEntryStatus.PROPOSED
    assert stored.resume_entries_revision == 1
    assert stored.trace[-1].event_type == "resume_entries_proposed"


@pytest.mark.parametrize("invalid_fact_id", ["missing-fact", "foreign-fact"])
def test_set_entries_rejects_missing_or_foreign_fact_provenance(
    invalid_fact_id: str,
) -> None:
    workflow, session_id, _fact_id = confirmed_workflow()
    if invalid_fact_id == "foreign-fact":
        other = workflow.create_session()
        workflow.update_profile(other.session_id, REQUIRED_FACTS, source_reference="message-2")
        workflow.confirm_profile(other.session_id)
        invalid_fact_id = next(
            fact.fact_id for fact in other.profile.facts if fact.field == "project"
        )

    with pytest.raises(InvalidTransitionError, match="confirmed fact"):
        workflow.set_resume_entries(session_id, [proposed_entry(invalid_fact_id)])

    session = workflow.get_session(session_id)
    assert session.resume_entries == []
    assert session.state is SessionState.PROFILE_CONFIRMED


def test_edit_preserves_citations_marks_entry_for_review_and_invalidates_downstream() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry_id = workflow.get_session(session_id).resume_entries[0].entry_id
    workflow.approve_resume_entry(session_id, entry_id, [])
    session = workflow.get_session(session_id)
    session.state = SessionState.CV_VALIDATED
    session.selected_job_id = "job-1"

    revised = workflow.update_resume_entry(
        session_id,
        entry_id,
        ResumeEntryEdit(
            heading="Scheduling API",
            organisation_or_context="UTS coursework",
            details=["Python"],
            bullets=["Built a scheduling API with Python."],
        ),
    )

    edited = revised.resume_entries[0]
    assert edited.status is ResumeEntryStatus.NEEDS_REVIEW
    assert edited.heading.fact_ids == [fact_id]
    assert edited.details[0].label == "Technologies"
    assert edited.details[0].value.fact_ids == [fact_id]
    assert edited.bullets[0].fact_ids == [fact_id]
    assert revised.selected_job_id is None
    assert revised.state is SessionState.RESUME_ENTRIES_REVIEW
    assert revised.trace[-1].event_type == "resume_entry_updated"


def test_only_substantive_approved_entries_unlock_retrieval() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    skills_entry = proposed_entry(fact_id)
    skills_entry.kind = ResumeEntryKind.SKILLS
    workflow.set_resume_entries(session_id, [skills_entry])
    entry_id = workflow.get_session(session_id).resume_entries[0].entry_id
    issue = ResumeEntryValidationIssue(
        entry_id=entry_id,
        severity=ValidationSeverity.WARNING,
        code="interpretive_language",
        message="This wording is interpretive but grounded in the source fact.",
    )

    reviewed = workflow.approve_resume_entry(session_id, entry_id, [issue])

    assert reviewed.state is SessionState.RESUME_ENTRIES_REVIEW
    assert workflow.approved_resume_entries(reviewed)[0].entry_id == entry_id
    assert reviewed.resume_entry_validation_issues == [issue]
    with pytest.raises(InvalidTransitionError, match="needs-review"):
        workflow.approve_resume_entry(session_id, entry_id, [])

    substantive = proposed_entry(fact_id)
    workflow.set_resume_entries(session_id, [substantive])
    substantive_id = workflow.get_session(session_id).resume_entries[0].entry_id
    approved = workflow.approve_resume_entry(session_id, substantive_id, [])

    assert approved.state is SessionState.RESUME_ENTRIES_APPROVED


def test_approval_rejects_linked_entry_until_revised_fact_is_reconfirmed() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry_id = workflow.get_session(session_id).resume_entries[0].entry_id
    workflow.approve_resume_entry(session_id, entry_id, [])
    workflow.update_profile(
        session_id,
        [FactInput(field="project", value="Built a revised course-planning API")],
        source_reference="message-2",
    )

    with pytest.raises(InvalidTransitionError, match="confirmed fact"):
        workflow.approve_resume_entry(session_id, entry_id, [])

    entry = workflow.get_session(session_id).resume_entries[0]
    assert entry.status is ResumeEntryStatus.NEEDS_REVIEW


def test_deleting_entry_keeps_profile_fact_and_reconciles_review_state() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry_id = workflow.get_session(session_id).resume_entries[0].entry_id
    workflow.approve_resume_entry(session_id, entry_id, [])

    revised = workflow.delete_resume_entry(session_id, entry_id)

    assert revised.resume_entries == []
    assert any(fact.fact_id == fact_id for fact in revised.profile.facts)
    assert revised.state is SessionState.RESUME_ENTRIES_REVIEW
    assert revised.trace[-1].event_type == "resume_entry_removed"


def entry_service(workflow, entries=(), issues=(), error=None):
    from app.services.resume_entries import ResumeEntryService

    class Provider:
        def propose_resume_entries(self, confirmed_facts):
            assert all(fact.status is FactStatus.CONFIRMED for fact in confirmed_facts)
            if error:
                raise error
            return list(entries)

        def validate_resume_entries(self, entries, confirmed_facts):
            assert all(fact.status is FactStatus.CONFIRMED for fact in confirmed_facts)
            if error:
                raise error
            return list(issues)

    return ResumeEntryService(workflow, Provider())


def test_set_entries_rejects_draft_fact_provenance_atomically() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.get_session(session_id)
    next(f for f in session.profile.facts if f.fact_id == fact_id).status = FactStatus.DRAFT
    before = session.model_dump()
    with pytest.raises(InvalidTransitionError, match="confirmed fact"):
        workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    assert session.model_dump() == before


def test_service_proposes_only_after_profile_confirmation_and_never_auto_approves() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    entry = proposed_entry(fact_id)
    entry.status = ResumeEntryStatus.APPROVED
    service = entry_service(workflow, [entry])
    empty = workflow.create_session()
    with pytest.raises(InvalidTransitionError, match="Confirm the profile"):
        service.propose(empty.session_id)
    result = service.propose(session_id)
    assert result.state is SessionState.RESUME_ENTRIES_REVIEW
    assert result.resume_entries[0].status is ResumeEntryStatus.PROPOSED


@pytest.mark.parametrize("failure", ["foreign", "union", "draft", "malformed", "unavailable"])
def test_service_proposal_failure_leaves_previous_review_unchanged(failure) -> None:
    from app.services.resume_entries import ResumeEntryEvidenceError

    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry = proposed_entry(fact_id)
    error = None
    expected = ResumeEntryEvidenceError
    if failure == "foreign":
        entry.bullets[0].fact_ids = ["foreign-fact"]
    elif failure == "union":
        entry.source_fact_ids = []
    elif failure == "draft":
        next(f for f in session.profile.facts if f.fact_id == fact_id).status = FactStatus.DRAFT
    elif failure == "malformed":
        error = ProviderProtocolError("No structured proposal")
        expected = ProviderProtocolError
    else:
        error = ProviderUnavailableError("Unavailable")
        expected = ProviderUnavailableError
    before = session.model_dump()
    with pytest.raises(expected):
        entry_service(workflow, [proposed_entry(fact_id), entry], error=error).propose(session_id)
    assert session.model_dump() == before


@pytest.mark.parametrize("invalid", ["unknown", "foreign", "draft", "deleted", "union", "empty"])
def test_service_approval_rechecks_all_evidence_before_provider_and_mutation(invalid) -> None:
    from app.services.resume_entries import ResumeEntryEvidenceError

    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry = session.resume_entries[0]
    fact = next(f for f in session.profile.facts if f.fact_id == fact_id)
    if invalid == "draft":
        fact.status = FactStatus.DRAFT
    elif invalid == "deleted":
        session.profile.facts.remove(fact)
    elif invalid == "union":
        entry.source_fact_ids = []
    elif invalid == "empty":
        entry.details[0].value.fact_ids = []
    else:
        invalid_id = "missing-fact"
        if invalid == "foreign":
            other = workflow.create_session()
            workflow.update_profile(other.session_id, REQUIRED_FACTS, source_reference="other")
            workflow.confirm_profile(other.session_id)
            invalid_id = other.profile.facts[0].fact_id
        entry.organisation_or_context.fact_ids = [invalid_id]
    before = session.model_dump()
    service = entry_service(workflow, error=AssertionError("Provider must not run"))
    with pytest.raises(ResumeEntryEvidenceError, match="confirmed profile fact"):
        service.approve(session_id, entry.entry_id)
    assert session.model_dump() == before


@pytest.mark.parametrize("severity", [ValidationSeverity.ERROR, ValidationSeverity.WARNING])
def test_service_approval_blocks_errors_but_stores_accepted_warnings(severity) -> None:
    from app.services.resume_entries import ResumeEntryEvidenceError

    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry = session.resume_entries[0]
    issue = ResumeEntryValidationIssue(
        entry_id=entry.entry_id, severity=severity, code="interpretation", message="Review wording."
    )
    service = entry_service(workflow, issues=[issue])
    before = session.model_dump()
    if severity is ValidationSeverity.ERROR:
        with pytest.raises(ResumeEntryEvidenceError, match="not confirmed"):
            service.approve(session_id, entry.entry_id)
        assert session.model_dump() == before
    else:
        assert (
            service.approve(session_id, entry.entry_id).state
            is SessionState.RESUME_ENTRIES_APPROVED
        )
        assert session.resume_entry_validation_issues == [issue]


def test_service_edit_preserves_evidence_and_delete_preserves_profile() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    service = entry_service(workflow, [proposed_entry(fact_id)])
    session = service.propose(session_id)
    entry = session.resume_entries[0]
    service.approve(session_id, entry.entry_id)
    service.edit(
        session_id,
        entry.entry_id,
        ResumeEntryEdit(
            heading="API project",
            organisation_or_context="Coursework",
            details=["Python"],
            bullets=["Built the course-planning API."],
        ),
    )
    assert entry.status is ResumeEntryStatus.NEEDS_REVIEW
    assert entry.bullets[0].fact_ids == [fact_id]
    service.delete(session_id, entry.entry_id)
    assert session.resume_entries == []
    assert any(f.fact_id == fact_id for f in session.profile.facts)


def test_approving_another_entry_keeps_previously_accepted_warning() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    first, second = proposed_entry(fact_id), proposed_entry(fact_id)
    session = workflow.set_resume_entries(session_id, [first, second])
    warning = ResumeEntryValidationIssue(
        entry_id=first.entry_id,
        severity=ValidationSeverity.WARNING,
        code="interpretive_language",
        message="Review wording",
    )
    entry_service(workflow, issues=[warning]).approve(session_id, first.entry_id)
    entry_service(workflow).approve(session_id, second.entry_id)
    assert session.resume_entry_validation_issues == [warning]


@pytest.mark.parametrize("failure", ["unavailable", "malformed", "wrong_entry", "invalid_severity"])
def test_failed_entry_audit_is_atomic(failure) -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry = session.resume_entries[0]
    issues = []
    error = None
    expected = ProviderProtocolError
    if failure == "unavailable":
        error = ProviderUnavailableError("Unavailable")
        expected = ProviderUnavailableError
    elif failure == "malformed":
        issues = [object()]
    else:
        issue = ResumeEntryValidationIssue(
            entry_id=entry.entry_id, code="audit", message="Review wording"
        )
        if failure == "wrong_entry":
            issue.entry_id = "other-entry"
        else:
            issue.severity = "invalid"
        issues = [issue]
    before = session.model_dump()
    with pytest.raises(expected):
        entry_service(workflow, issues=issues, error=error).approve(session_id, entry.entry_id)
    assert session.model_dump() == before


def test_invalid_late_display_field_does_not_partially_edit_entry() -> None:
    from app.services.resume_entries import ResumeEntryEvidenceError

    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    before = session.model_dump()
    with pytest.raises(ResumeEntryEvidenceError):
        entry_service(workflow).edit(
            session_id,
            session.resume_entries[0].entry_id,
            ResumeEntryEdit(
                heading="Changed heading",
                organisation_or_context="Coursework",
                details=["x" * 1001],
                bullets=["Built the API"],
            ),
        )
    assert session.model_dump() == before


def test_editing_another_entry_keeps_previously_accepted_warning() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    first, second = proposed_entry(fact_id), proposed_entry(fact_id)
    session = workflow.set_resume_entries(session_id, [first, second])
    warning = ResumeEntryValidationIssue(
        entry_id=first.entry_id,
        severity=ValidationSeverity.WARNING,
        code="interpretive_language",
        message="Review wording",
    )
    entry_service(workflow, issues=[warning]).approve(session_id, first.entry_id)
    entry_service(workflow).edit(
        session_id,
        second.entry_id,
        ResumeEntryEdit(
            heading="API project",
            organisation_or_context="Coursework",
            details=["Python"],
            bullets=["Built the API."],
        ),
    )
    assert session.resume_entry_validation_issues == [warning]


def test_duplicate_proposed_entry_ids_leave_session_unchanged() -> None:
    workflow, session_id, fact_id = confirmed_workflow()
    entry = proposed_entry(fact_id)
    session = workflow.get_session(session_id)
    before = session.model_dump()
    with pytest.raises(ProviderProtocolError, match="unique"):
        entry_service(workflow, [entry, entry.model_copy(deep=True)]).propose(session_id)
    assert session.model_dump() == before


@pytest.mark.parametrize(
    "change", ["wording", "wording_restored", "source_reconfirmed", "replacement", "deletion"]
)
def test_approval_rejects_a_review_changed_during_its_audit(change: str) -> None:
    from app.services.resume_entries import ResumeEntryService

    workflow, session_id, fact_id = confirmed_workflow()
    session = workflow.set_resume_entries(session_id, [proposed_entry(fact_id)])
    entry_id = session.resume_entries[0].entry_id
    edit = ResumeEntryEdit(
        heading="Course-planning API",
        organisation_or_context="UTS coursework",
        details=["Python"],
        bullets=["Built a course-planning API with Python."],
    )
    # A second edit leaves status needs_review: checking status alone is insufficient.
    workflow.update_resume_entry(session_id, entry_id, edit)
    after_change = {}

    def change_review() -> None:
        if change in {"wording", "wording_restored"}:
            workflow.update_resume_entry(
                session_id, entry_id, edit.model_copy(update={"heading": "Led 50 engineers"})
            )
            if change == "wording_restored":
                workflow.update_resume_entry(session_id, entry_id, edit)
        elif change == "source_reconfirmed":
            workflow.update_profile(
                session_id,
                [FactInput(field="project", value="Observed someone else build an API")],
                source_reference="message-2",
            )
            workflow.confirm_profile(session_id)
        elif change == "replacement":
            replacement = proposed_entry(session.profile.facts[1].fact_id)
            replacement.entry_id = entry_id
            workflow.set_resume_entries(session_id, [replacement])
        else:
            workflow.delete_resume_entry(session_id, entry_id)
        after_change.update(session.model_dump())

    class InterleavingProvider:
        def propose_resume_entries(self, confirmed_facts):
            raise AssertionError("Proposal is outside this approval test")

        def validate_resume_entries(self, entries, confirmed_facts):
            # Wait for a real second thread to finish the change while the audit is in flight.
            # The timeout detects a held session lock; ordering does not depend on sleeps.
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                executor.submit(change_review).result(timeout=5)
            finally:
                executor.shutdown(wait=False)
            assert entries[0].heading.text == "Course-planning API"
            if change == "wording_restored":
                # A -> B -> A restored every audited field, citation and status.
                assert session.resume_entries[0] == entries[0]
                assert session.resume_entries[0].status is ResumeEntryStatus.NEEDS_REVIEW
            assert next(f for f in confirmed_facts if f.fact_id == fact_id).value == (
                "Built a course-planning API with Python"
            )
            return []

    with pytest.raises(InvalidTransitionError, match="changed"):
        ResumeEntryService(workflow, InterleavingProvider()).approve(session_id, entry_id)

    assert session.model_dump() == after_change
    assert not workflow.approved_resume_entries(session)
