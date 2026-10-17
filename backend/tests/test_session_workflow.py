from uuid import UUID

import pytest

from app.domain.models import (
    CVClaim,
    CVDocument,
    FactInput,
    FactStatus,
    ResumeEntry,
    ResumeEntryKind,
    ResumeText,
    RetrievalResult,
    RetrievalScoreBreakdown,
    SessionState,
)
from app.domain.workflow import (
    InvalidTransitionError,
    SessionNotFoundError,
    SessionWorkflow,
)

REQUIRED_FACTS = [
    FactInput(field="name", value="Maya Chen"),
    FactInput(field="education", value="Third-year Bachelor of Computing Science at UTS"),
    FactInput(field="skills", value="Python, SQL, REST APIs"),
    FactInput(field="experience", value="Built a team course-planning API"),
    FactInput(field="target_role", value="Software Engineering Intern"),
]


def test_sessions_are_uuid_keyed_and_isolated() -> None:
    workflow = SessionWorkflow()

    first = workflow.create_session()
    second = workflow.create_session()

    assert UUID(first.session_id)
    assert UUID(second.session_id)
    assert first.session_id != second.session_id

    workflow.update_profile(
        first.session_id,
        [FactInput(field="name", value="Maya Chen")],
        source_reference="message-1",
    )

    assert workflow.get_session(first.session_id).profile.facts[0].value == "Maya Chen"
    assert workflow.get_session(second.session_id).profile.facts == []


def test_updating_a_field_preserves_its_fact_id_and_requires_reconfirmation() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()

    updated = workflow.update_profile(
        session.session_id,
        REQUIRED_FACTS,
        source_reference="message-1",
    )
    original_name_id = next(f.fact_id for f in updated.profile.facts if f.field == "name")
    confirmed = workflow.confirm_profile(session.session_id)

    assert confirmed.state is SessionState.PROFILE_CONFIRMED
    assert all(f.status is FactStatus.CONFIRMED for f in confirmed.profile.facts)

    revised = workflow.update_profile(
        session.session_id,
        [FactInput(field="name", value="Maya L. Chen")],
        source_reference="message-2",
    )
    name_fact = next(f for f in revised.profile.facts if f.field == "name")

    assert name_fact.fact_id == original_name_id
    assert name_fact.status is FactStatus.DRAFT
    assert name_fact.source.reference == "message-2"
    assert revised.state is SessionState.PROFILE_REVIEW


def test_confirmation_lists_missing_required_profile_fields() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    workflow.update_profile(
        session.session_id,
        [FactInput(field="name", value="Maya Chen")],
        source_reference="message-1",
    )

    with pytest.raises(InvalidTransitionError) as error:
        workflow.confirm_profile(session.session_id)

    assert set(error.value.details["missing_fields"]) == {
        "education",
        "skills",
        "experience_or_project",
        "target_role",
    }


def test_profile_revision_invalidates_all_downstream_work() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    workflow.update_profile(session.session_id, REQUIRED_FACTS, source_reference="message-1")
    workflow.confirm_profile(session.session_id)

    project_fact_id = next(
        fact.fact_id for fact in session.profile.facts if fact.field == "experience"
    )
    workflow.set_resume_entries(
        session.session_id,
        [
            ResumeEntry(
                kind=ResumeEntryKind.EXPERIENCE,
                heading=ResumeText(text="Course-planning API", fact_ids=[project_fact_id]),
                source_fact_ids=[project_fact_id],
            )
        ],
    )
    entry_id = session.resume_entries[0].entry_id
    workflow.approve_resume_entry(session.session_id, entry_id, [])

    stored = workflow.get_session(session.session_id)
    stored.state = SessionState.CV_VALIDATED
    stored.retrieval_results = [
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
            excerpt="Build reliable APIs.",
            match_reasons=["Python"],
            eligibility_notes=["Eligibility is not asserted."],
        )
    ]
    stored.selected_job_id = "job-1"
    stored.cv = CVDocument(
        cv_id="cv-1",
        target_job_id="job-1",
        headline="Software Engineering Student",
        claims=[CVClaim(claim_id="claim-1", text="Built an API.", fact_ids=["fact-1"])],
    )
    stored.validated_content_hash = "old-hash"

    revised = workflow.update_profile(
        session.session_id,
        [FactInput(field="experience", value="Built a revised course-planning API")],
        source_reference="message-2",
    )

    assert revised.state is SessionState.PROFILE_REVIEW
    assert revised.retrieval_results == []
    assert revised.selected_job_id is None
    assert revised.cv is None
    assert revised.validated_content_hash is None
    assert revised.resume_entries[0].status.value == "needs_review"
    assert revised.resume_entries_revision == 3


def test_unknown_session_is_not_silently_created() -> None:
    workflow = SessionWorkflow()

    with pytest.raises(SessionNotFoundError):
        workflow.get_session("not-a-real-session")
