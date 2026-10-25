"""Rich-profile regressions: labels must not hide evidence or merge distinct facts."""

import pytest

from app.domain.models import (
    Fact,
    FactInput,
    FactSource,
    FactSourceType,
    FactStatus,
    Job,
    ProfileDraft,
)
from app.domain.workflow import InvalidTransitionError, SessionWorkflow
from app.providers.base import ProviderTurn, ToolCall
from app.providers.fake import ScriptedProvider
from app.services.agent import AgentService
from app.services.retrieval import (
    _match_reasons,
    _matched_skills,
    _missing_requirements,
    build_job_match_profile,
    build_profile_query,
    score_job_evidence,
)


def confirmed(field: str, value: str = "Python") -> Fact:
    return Fact(
        field=field,
        value=value,
        status=FactStatus.CONFIRMED,
        source=FactSource(source_type=FactSourceType.USER_MESSAGE, reference="message-rich"),
    )


def python_job() -> Job:
    return Job(
        document_id="python",
        title="Python Engineer",
        description="Responsibilities: Python. Requirements: Python.",
    )


@pytest.mark.parametrize(
    "field",
    [
        "experience_startup",
        "experience_internship",
        "other_experience",
        "work_experience",
        "internships",
        "projects",
        "project_retrieval",
        "research_finance",
        "Experience: Internship",
    ],
)
def test_named_work_is_sufficient_for_confirmation_without_relabelling(field: str) -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    workflow.update_profile(
        session.session_id,
        [
            FactInput(field="name", value="Demo Candidate"),
            FactInput(field="education", value="Bachelor of Computing Science"),
            FactInput(field="skills", value="Python"),
            FactInput(field="target_role", value="AI Engineer"),
            FactInput(field=field, value="Built Python retrieval services."),
        ],
        source_reference="message-rich",
    )
    before = session.profile.model_dump()

    workflow.confirm_profile(session.session_id)

    assert session.state.value == "profile_confirmed"
    assert all(f.status is FactStatus.CONFIRMED for f in session.profile.facts)
    assert [
        (f.field, f.fact_id, f.value, f.source.model_dump()) for f in session.profile.facts
    ] == [(f["field"], f["fact_id"], f["value"], f["source"]) for f in before["facts"]]


def test_a_named_company_field_does_not_satisfy_candidate_identity() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    session.profile = ProfileDraft(
        facts=[
            confirmed("name_company", "Example Company"),
            confirmed("education", "Bachelor of Computing Science"),
            confirmed("skills", "Python"),
            confirmed("experience_internship", "Built Python pipelines"),
            confirmed("target_role", "AI Engineer"),
        ]
    )
    assert workflow.missing_required_fields(session) == ["name"]


@pytest.mark.parametrize(
    ("field", "component"),
    [
        ("experience_startup", "experience_score"),
        ("other_experience", "experience_score"),
        ("internships", "experience_score"),
        ("projects", "project_score"),
        ("project_retrieval", "project_score"),
        ("research_finance", "project_score"),
        ("education_prior", "education_score"),
        ("technical_skills", "skill_score"),
        ("Skills: Languages", "skill_score"),
        ("skills_machine_learning", "skill_score"),
        ("experience_machine_learning", "experience_score"),
        ("project_machine_learning", "project_score"),
    ],
)
def test_named_fact_contributes_to_its_own_matching_component(field: str, component: str) -> None:
    profile = ProfileDraft(facts=[confirmed(field)])
    job = python_job()

    score = score_job_evidence(profile, build_job_match_profile(job), 0.5)

    assert getattr(score, component) == 1.0
    for other in {"experience_score", "project_score", "education_score", "skill_score"} - {
        component
    }:
        assert getattr(score, other) == 0.0
    assert _match_reasons(profile, job)
    assert _missing_requirements(profile, job) == []


def test_skill_alias_appears_in_matched_skills() -> None:
    profile = ProfileDraft(facts=[confirmed("Skills: Languages", "Python, SQL")])
    assert _matched_skills(profile, python_job()) == ["Python"]


@pytest.mark.parametrize(
    ("field", "status", "value"),
    [
        ("experience_internship", FactStatus.DRAFT, "Python"),
        ("projects", FactStatus.CONFIRMED, "Planning to build Python services"),
        ("experience_startup", FactStatus.CONFIRMED, "No Python experience"),
    ],
)
def test_named_facts_still_require_confirmed_non_aspirational_evidence(
    field: str, status: FactStatus, value: str
) -> None:
    fact = confirmed(field, value)
    fact.status = status
    profile = ProfileDraft(facts=[fact])
    job = python_job()
    assert score_job_evidence(profile, build_job_match_profile(job), 0.5).evidence_score == 0.0
    assert _match_reasons(profile, job) == []
    assert _missing_requirements(profile, job) == ["Python"]


@pytest.mark.parametrize(
    "field", ["project_goal", "experience_goals", "skills_to_learn", "experience_contact_email"]
)
def test_intent_and_private_labels_cannot_satisfy_evidence(field: str) -> None:
    profile = ProfileDraft(facts=[confirmed(field)])
    job = python_job()
    assert score_job_evidence(profile, build_job_match_profile(job), 0.5).evidence_score == 0.0
    assert _match_reasons(profile, job) == []
    assert _matched_skills(profile, job) == []
    assert _missing_requirements(profile, job) == ["Python"]

    workflow = SessionWorkflow()
    session = workflow.create_session()
    session.profile = profile
    assert "experience_or_project" in workflow.missing_required_fields(session)
    with pytest.raises(InvalidTransitionError):
        workflow.confirm_profile(session.session_id)


def test_named_project_does_not_establish_professional_years_or_a_degree() -> None:
    job = Job(
        document_id="senior",
        title="Python Engineer",
        description=(
            "Requirements: three years of Python experience; a master's degree in computing."
        ),
    )
    project = ProfileDraft(facts=[confirmed("projects", "Three years of Python coursework")])
    assert _missing_requirements(project, job) == [
        "three years of Python experience",
        "a master's degree in computing",
    ]
    work = ProfileDraft(facts=[confirmed("internship_acme", "Three years of Python experience")])
    assert _missing_requirements(work, job) == ["a master's degree in computing"]


def test_rich_query_preserves_all_named_work_and_is_order_independent() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed("experience_b", "Built APIs"),
            confirmed("projects", "Built retrieval models"),
            confirmed("experience_a", "Built data pipelines"),
            confirmed("education_prior", "Diploma in IT"),
            confirmed("technical_skills", "Python"),
            confirmed("contact", "private@example.test"),
        ]
    )
    query = build_profile_query(profile)
    assert query == (
        "skills: Python\neducation: Diploma in IT\nexperience: Built data pipelines\n"
        "experience: Built APIs\nproject: Built retrieval models"
    )
    profile.facts.reverse()
    assert build_profile_query(profile) == query


def test_agent_retains_multiple_experiences_and_reports_server_completeness() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    facts = [
        {"field": "name", "value": "Demo Candidate"},
        {"field": "location", "value": "Sydney"},
        {"field": "contact", "value": "candidate@example.test"},
        {"field": "education", "value": "Bachelor of Computing Science"},
        {"field": "education_prior", "value": "Diploma of Information Technology"},
        {"field": "education_recognition", "value": "Academic merit award"},
        {"field": "skills", "value": "Python"},
        {"field": "target_role", "value": "AI Engineer"},
        {"field": "experience_startup", "value": "Built Python services"},
        {"field": "experience_product", "value": "Built a meal-planning application"},
        {"field": "experience_commerce", "value": "Tested commerce API boundaries"},
        {"field": "experience_internship", "value": "Built Python data pipelines"},
        {"field": "projects", "value": "Built a retrieval assistant"},
        {"field": "research_finance", "value": "Evaluated financial retrieval"},
        {"field": "research_language", "value": "Evaluated language models"},
        {"field": "other_experience", "value": "Tutored programming and SQL"},
    ]
    provider = ScriptedProvider(
        [
            ProviderTurn(
                tool_calls=[
                    ToolCall(call_id="rich", name="update_profile", arguments={"facts": facts})
                ]
            ),
            ProviderTurn(message="Please review and confirm your facts."),
        ]
    )
    service = AgentService(workflow, provider, retrieve_jobs=lambda _: {}, generate_cv=lambda _: {})

    result = service.handle_message(
        session.session_id, "My work includes multiple roles and projects."
    )

    assert result.observations[0].success
    assert result.observations[0].result["missing_fields"] == []
    assert session.state.value == "profile_review"  # The agent still cannot confirm.
    assert [f.field for f in session.profile.facts] == [f["field"] for f in facts]
    ids = {f.field: f.fact_id for f in session.profile.facts}
    assert len(set(ids.values())) == len(facts)
    workflow.confirm_profile(session.session_id)
    workflow.update_profile(
        session.session_id,
        [FactInput(field="experience_internship", value="Updated internship description")],
        source_reference="message-correction",
    )
    assert {f.field: f.fact_id for f in session.profile.facts} == ids
    assert next(f.value for f in session.profile.facts if f.field == "experience_startup") == (
        "Built Python services"
    )
    assert next(f for f in session.profile.facts if f.field == "experience_internship").status == (
        FactStatus.DRAFT
    )


@pytest.mark.parametrize(
    "field", ["employer_email", "contact_password", "project_url", "private_phone", "email_secret"]
)
def test_contact_aliases_do_not_admit_unrelated_or_private_fields(field):
    from app.domain.profile_fields import is_contact_field

    assert not is_contact_field(field)
