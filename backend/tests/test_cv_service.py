from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.models import (
    CVClaim,
    CVDocument,
    FactInput,
    FactStatus,
    Job,
    ResumeEntry,
    ResumeEntryKind,
    ResumeEntryStatus,
    ResumeText,
    RetrievalResult,
    RetrievalScoreBreakdown,
    SessionState,
    ValidationIssue,
    ValidationSeverity,
)
from app.domain.workflow import InvalidTransitionError, SessionWorkflow
from app.providers.fake import ScriptedCVProvider
from app.services.cv import CVEvidenceError, CVService, cv_content_hash


@pytest.mark.parametrize("contact_field", ["email", "contact_email", "email_address", "portfolio"])
def test_cv_generation_uses_only_contact_and_approved_entries_for_two_jobs(contact_field) -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    contact = session.profile.facts[0].model_copy(
        update={"field": contact_field, "value": "maya@test.edu"}
    )
    contact.fact_id = "fact-email"
    session.profile.facts.append(contact)
    draft_phone = contact.model_copy(
        update={"field": "phone", "status": FactStatus.DRAFT, "fact_id": "fact-phone"}
    )
    session.profile.facts.append(draft_phone)
    session.resume_entries.append(
        session.resume_entries[0].model_copy(
            update={"entry_id": "unapproved", "status": ResumeEntryStatus.PROPOSED}, deep=True
        )
    )
    before = [e.model_dump() for e in session.resume_entries]

    class NarrowProvider(ScriptedCVProvider):
        def generate_cv(self, contact_facts, approved_entries, job):
            assert {f.field for f in contact_facts} == {"name", contact_field}
            assert [e.entry_id for e in approved_entries] == [session.resume_entries[0].entry_id]
            return CVDocument(
                target_job_id=job.document_id,
                headline="API project" if job.document_id == "job-1" else "Course-planning project",
                headline_fact_ids=approved_entries[0].heading.fact_ids,
            )

    service = CVService(
        workflow, NarrowProvider(generated=CVDocument(target_job_id="unused", headline="unused"))
    )
    first = service.generate(session_id, job)
    service.validate(session_id, first.cv_id)
    assert service.can_export(session_id, first.cv_id)
    service.record_export(session_id, first.cv_id)
    second_job = job.model_copy(update={"document_id": "job-2", "title": "Data Intern"})
    session.retrieval_results.append(
        session.retrieval_results[0].model_copy(update={"document_id": "job-2"})
    )
    workflow.select_job(session_id, "job-2")
    assert session.cv is None
    assert session.validated_content_hash is None
    second = service.generate(session_id, second_job)
    assert first.target_job_id == "job-1"
    assert second.target_job_id == "job-2"
    assert first.headline != second.headline
    assert first.cv_id != second.cv_id
    assert first.headline_fact_ids == second.headline_fact_ids
    assert set(second.headline_fact_ids).issubset({f.fact_id for f in session.profile.facts})
    assert service.can_export(session_id, second.cv_id) is False
    service.validate(session_id, second.cv_id)
    assert service.can_export(session_id, second.cv_id)
    assert [e.model_dump() for e in session.resume_entries] == before


@pytest.mark.parametrize("kind", [None, ResumeEntryKind.SKILLS])
def test_cv_generation_requires_a_substantive_approved_entry(kind) -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    if kind is None:
        session.resume_entries[0].status = ResumeEntryStatus.NEEDS_REVIEW
    else:
        session.resume_entries[0].kind = kind
    before = session.model_dump()
    with pytest.raises(InvalidTransitionError, match="substantive"):
        CVService(
            workflow,
            ScriptedCVProvider(
                generated=CVDocument(
                    target_job_id=job.document_id,
                    headline="Name",
                    headline_fact_ids=[session.profile.facts[0].fact_id],
                )
            ),
        ).generate(session_id, job)
    assert session.model_dump() == before


REQUIRED_FACTS = [
    FactInput(field="name", value="Maya Chen"),
    FactInput(field="education", value="Bachelor of Computing Science at UTS"),
    FactInput(field="skills", value="Python, SQL, REST APIs"),
    FactInput(field="project", value="Built a course-planning API with Python"),
    FactInput(field="target_role", value="Software Engineering Intern"),
]


def prepared_workflow() -> tuple[SessionWorkflow, str, Job]:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    workflow.update_profile(session.session_id, REQUIRED_FACTS, source_reference="message-1")
    workflow.confirm_profile(session.session_id)
    project_fact_id = next(
        fact.fact_id for fact in session.profile.facts if fact.field == "project"
    )
    workflow.set_resume_entries(
        session.session_id,
        [
            ResumeEntry(
                kind=ResumeEntryKind.PROJECT,
                heading=ResumeText(text="Course-planning API", fact_ids=[project_fact_id]),
                source_fact_ids=[project_fact_id],
            )
        ],
    )
    workflow.approve_resume_entry(session.session_id, session.resume_entries[0].entry_id, [])
    workflow.set_retrieval_results(
        session.session_id,
        [
            RetrievalResult(
                document_id="job-1",
                title="Software Engineer",
                score=0.91,
                score_breakdown=RetrievalScoreBreakdown(
                    semantic_score=0.91,
                    project_score=0.0,
                    skill_score=0.0,
                    target_role_score=0.0,
                    education_score=0.0,
                    experience_score=0.0,
                    evidence_score=0.0,
                    final_score=0.91,
                ),
                excerpt="Build reliable Python APIs.",
                match_reasons=["skills: python"],
                eligibility_notes=["Verify eligibility."],
            )
        ],
    )
    workflow.select_job(session.session_id, "job-1")
    return (
        workflow,
        session.session_id,
        Job(
            document_id="job-1",
            title="Software Engineer",
            description="Build reliable Python APIs. Five years of experience required.",
        ),
    )


def test_job_selection_must_reference_a_retrieved_job() -> None:
    workflow, session_id, _job = prepared_workflow()

    with pytest.raises(InvalidTransitionError, match="retrieved"):
        workflow.select_job(session_id, "not-retrieved")


def test_generation_rejects_claims_that_cite_job_requirements_as_candidate_facts() -> None:
    workflow, session_id, job = prepared_workflow()
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Software Engineer",
            claims=[
                CVClaim(
                    text="Has five years of professional experience.",
                    fact_ids=[job.document_id],
                )
            ],
        )
    )

    with pytest.raises(CVEvidenceError, match="confirmed fact"):
        CVService(workflow, provider).generate(session_id, job)


def test_validated_cv_gets_a_content_hash_and_can_be_exported() -> None:
    workflow, session_id, job = prepared_workflow()
    fact_id = next(
        fact.fact_id
        for fact in workflow.get_session(session_id).profile.facts
        if fact.field == "project"
    )
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[
                CVClaim(
                    text="Built a course-planning API with Python.",
                    fact_ids=[fact_id],
                )
            ],
        ),
        validation_issues=[],
    )
    service = CVService(workflow, provider)

    draft = service.generate(session_id, job)
    validated = service.validate(session_id, draft.cv_id)

    assert validated.state is SessionState.CV_VALIDATED
    assert validated.cv is not None
    assert validated.cv.claims[0].verified is True
    assert validated.validated_content_hash == cv_content_hash(validated.cv)
    assert service.can_export(session_id, draft.cv_id) is True

    exported = service.record_export(session_id, draft.cv_id)
    assert exported.state is SessionState.PDF_EXPORTED


def test_interpretive_warning_does_not_block_export() -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student contributing to backend-focused projects",
            headline_fact_ids=[session.profile.facts[1].fact_id, session.profile.facts[3].fact_id],
        ),
        validation_issues=[
            ValidationIssue(
                claim_id="headline",
                code="interpretive_language",
                severity=ValidationSeverity.WARNING,
                message=(
                    "The phrase backend-focused is interpretive wording grounded in "
                    "the cited facts."
                ),
            )
        ],
    )
    service = CVService(workflow, provider)

    draft = service.generate(session_id, job)
    validated = service.validate(session_id, draft.cv_id)

    assert validated.state is SessionState.CV_VALIDATED
    assert validated.validation_issues[0].severity is ValidationSeverity.WARNING
    assert service.can_export(session_id, draft.cv_id) is True


def test_unsupported_claim_blocks_export() -> None:
    workflow, session_id, job = prepared_workflow()
    fact_id = workflow.get_session(session_id).profile.facts[0].fact_id
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[CVClaim(text="Expert engineer.", fact_ids=[fact_id])],
        ),
        validation_issues=[
            ValidationIssue(
                claim_id="claim-from-provider",
                code="not_entailed",
                message="The cited name fact does not support expertise.",
            )
        ],
    )
    service = CVService(workflow, provider)
    draft = service.generate(session_id, job)

    validated = service.validate(session_id, draft.cv_id)

    assert validated.state is SessionState.CV_DRAFT
    assert validated.validated_content_hash is None
    assert service.can_export(session_id, draft.cv_id) is False
    with pytest.raises(InvalidTransitionError, match="validated CV"):
        service.record_export(session_id, draft.cv_id)


def test_claim_referencing_a_deleted_fact_blocks_export() -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    project_fact = next(fact for fact in session.profile.facts if fact.field == "project")
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[
                CVClaim(
                    text="Built a course-planning API with Python.",
                    fact_ids=[project_fact.fact_id],
                )
            ],
        )
    )
    service = CVService(workflow, provider)
    draft = service.generate(session_id, job)
    session.profile.facts.remove(project_fact)

    validated = service.validate(session_id, draft.cv_id)

    assert [issue.code for issue in validated.validation_issues] == ["unknown_fact_reference"]
    assert validated.state is SessionState.CV_DRAFT
    assert validated.validated_content_hash is None
    with pytest.raises(InvalidTransitionError, match="validated CV"):
        service.record_export(session_id, draft.cv_id)


def test_claim_referencing_another_sessions_fact_blocks_export() -> None:
    workflow, session_id, job = prepared_workflow()
    other_session = workflow.create_session()
    workflow.update_profile(other_session.session_id, REQUIRED_FACTS, source_reference="message-2")
    workflow.confirm_profile(other_session.session_id)
    foreign_fact_id = next(
        fact.fact_id
        for fact in workflow.get_session(other_session.session_id).profile.facts
        if fact.field == "project"
    )
    own_fact_id = next(
        fact.fact_id
        for fact in workflow.get_session(session_id).profile.facts
        if fact.field == "project"
    )
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[
                CVClaim(
                    text="Built a course-planning API with Python.",
                    fact_ids=[own_fact_id],
                )
            ],
        )
    )
    service = CVService(workflow, provider)
    draft = service.generate(session_id, job)
    draft.claims[0].fact_ids = [foreign_fact_id]

    validated = service.validate(session_id, draft.cv_id)

    assert [issue.code for issue in validated.validation_issues] == ["unknown_fact_reference"]
    assert validated.state is SessionState.CV_DRAFT
    assert validated.validated_content_hash is None
    with pytest.raises(InvalidTransitionError, match="validated CV"):
        service.record_export(session_id, draft.cv_id)


def test_claim_referencing_an_unconfirmed_fact_blocks_export() -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    project_fact = next(fact for fact in session.profile.facts if fact.field == "project")
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[
                CVClaim(
                    text="Built a course-planning API with Python.",
                    fact_ids=[project_fact.fact_id],
                )
            ],
        )
    )
    service = CVService(workflow, provider)
    draft = service.generate(session_id, job)
    project_fact.status = FactStatus.DRAFT

    validated = service.validate(session_id, draft.cv_id)

    assert [issue.code for issue in validated.validation_issues] == ["unknown_fact_reference"]
    assert validated.state is SessionState.CV_DRAFT
    assert validated.validated_content_hash is None
    with pytest.raises(InvalidTransitionError, match="validated CV"):
        service.record_export(session_id, draft.cv_id)


def test_editing_a_validated_cv_invalidates_its_hash() -> None:
    workflow, session_id, job = prepared_workflow()
    fact_id = workflow.get_session(session_id).profile.facts[0].fact_id
    provider = ScriptedCVProvider(
        generated=CVDocument(
            target_job_id=job.document_id,
            headline="Computing Science student",
            headline_fact_ids=[workflow.get_session(session_id).profile.facts[1].fact_id],
            claims=[CVClaim(text="Maya Chen", fact_ids=[fact_id])],
        )
    )
    service = CVService(workflow, provider)
    draft = service.generate(session_id, job)
    service.validate(session_id, draft.cv_id)
    edited = draft.model_copy(deep=True)
    edited.headline = "Backend Software Engineer"

    session = service.update(session_id, draft.cv_id, edited)

    assert session.state is SessionState.CV_DRAFT
    assert session.validated_content_hash is None
    assert session.cv is not None
    assert all(claim.verified is False for claim in session.cv.claims)
    assert service.can_export(session_id, draft.cv_id) is False


def test_headline_without_confirmed_evidence_is_rejected() -> None:
    workflow, session_id, job = prepared_workflow()
    cv = CVDocument(
        target_job_id=job.document_id, headline="Senior engineer with ten years experience"
    )
    with pytest.raises(CVEvidenceError, match="confirmed fact"):
        CVService(workflow, ScriptedCVProvider(generated=cv)).generate(session_id, job)


def test_unsupported_headline_blocks_export_even_with_valid_references() -> None:
    workflow, session_id, job = prepared_workflow()
    fact = workflow.get_session(session_id).profile.facts[0]
    cv = CVDocument.model_validate(
        {
            "target_job_id": job.document_id,
            "headline": "Senior engineer with ten years experience",
            "headline_fact_ids": [fact.fact_id],
        }
    )
    service = CVService(
        workflow,
        ScriptedCVProvider(
            generated=cv,
            validation_issues=[
                ValidationIssue(
                    claim_id="headline",
                    code="not_entailed",
                    message="Name does not establish seniority.",
                )
            ],
        ),
    )
    draft = service.generate(session_id, job)
    result = service.validate(session_id, draft.cv_id)
    assert result.state is SessionState.CV_DRAFT
    assert result.validation_issues[0].claim_id == "headline"
    assert not service.can_export(session_id, draft.cv_id)


@pytest.mark.parametrize("invalid_reference", ["missing", "foreign", "unconfirmed"])
def test_deterministic_headline_audit_revokes_export(invalid_reference: str) -> None:
    workflow, session_id, job = prepared_workflow()
    fact = workflow.get_session(session_id).profile.facts[1]
    service = CVService(
        workflow,
        ScriptedCVProvider(
            generated=CVDocument(
                target_job_id=job.document_id,
                headline="Computing Science student",
                headline_fact_ids=[fact.fact_id],
            )
        ),
    )
    draft = service.generate(session_id, job)
    service.validate(session_id, draft.cv_id)
    assert service.can_export(session_id, draft.cv_id)
    if invalid_reference == "missing":
        draft.headline_fact_ids = []
    elif invalid_reference == "foreign":
        other = workflow.create_session()
        workflow.update_profile(other.session_id, REQUIRED_FACTS, source_reference="other")
        workflow.confirm_profile(other.session_id)
        draft.headline_fact_ids = [other.profile.facts[1].fact_id]
    else:
        fact.status = FactStatus.DRAFT
    result = service.validate(session_id, draft.cv_id)
    assert result.validation_issues[0].claim_id == "headline"
    assert not service.can_export(session_id, draft.cv_id)


@pytest.mark.parametrize("change", ["delete_entry", "revise_profile", "switch_job", "reselect_job"])
def test_generation_rejects_invalidated_workflow_without_restoring_export(change: str) -> None:
    workflow, session_id, job = prepared_workflow()
    session = workflow.get_session(session_id)
    entry = session.resume_entries[0]
    after_change = {}
    cv = CVDocument(
        target_job_id=job.document_id,
        headline="Course-planning API",
        headline_fact_ids=entry.heading.fact_ids,
    )

    def invalidate_workflow() -> None:
        if change == "delete_entry":
            workflow.delete_resume_entry(session_id, entry.entry_id)
        elif change == "revise_profile":
            workflow.update_profile(
                session_id,
                [FactInput(field="name", value="Updated name")],
                source_reference="message-2",
            )
        elif change == "switch_job":
            session.retrieval_results.append(
                session.retrieval_results[0].model_copy(update={"document_id": "job-2"})
            )
            workflow.select_job(session_id, "job-2")
        else:
            # The same selected ID still represents a newer explicit workflow choice.
            workflow.select_job(session_id, job.document_id)
        after_change.update(session.model_dump())

    class InterleavingProvider(ScriptedCVProvider):
        def generate_cv(self, contact_facts, approved_entries, job):
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                executor.submit(invalidate_workflow).result(timeout=5)
            finally:
                executor.shutdown(wait=False)
            assert contact_facts[0].value == "Maya Chen"
            assert approved_entries[0].status is ResumeEntryStatus.APPROVED
            return super().generate_cv(contact_facts, approved_entries, job)

    service = CVService(workflow, InterleavingProvider(generated=cv))
    with pytest.raises(InvalidTransitionError, match="changed"):
        service.generate(session_id, job)

    assert session.model_dump() == after_change
    assert session.cv is None
    assert session.validated_content_hash is None
    assert not service.can_export(session_id, cv.cv_id)
    with pytest.raises(InvalidTransitionError, match="current session CV"):
        service.validate(session_id, cv.cv_id)
    with pytest.raises(InvalidTransitionError, match="validated CV"):
        service.record_export(session_id, cv.cv_id)
