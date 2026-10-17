import importlib.util
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.models import (
    CVDocument,
    Fact,
    Job,
    ResumeEntry,
    ResumeEntryKind,
    ResumeEntryStatus,
    ResumeEntryValidationIssue,
    ResumeText,
    RetrievalResult,
    RetrievalScoreBreakdown,
    Session,
    SessionState,
    TraceEvent,
    ValidationIssue,
)
from app.domain.workflow import SessionWorkflow
from app.main import ApplicationServices
from app.providers.base import ProviderTurn, ToolCall
from app.services.cv import CVService
from app.services.live_evaluation import (
    LiveRunRecord,
    LiveTransition,
    export_outcome,
    profile_to_confirmed_facts,
    session_to_live_run_record,
)
from app.services.resume_entries import ResumeEntryService
from app.services.retrieval import JobRepository, RetrievalService

RUNNER_PATH = Path(__file__).parents[2] / "scripts" / "run_live_evaluation.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("run_live_evaluation", RUNNER_PATH)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)
SCENARIOS = RUNNER.SCENARIOS
main = RUNNER.main


def test_live_run_record_rejects_key_like_text() -> None:
    with pytest.raises(ValidationError):
        LiveRunRecord(
            run_id="run-1",
            profile_id="student_profile_01",
            note="sk-proj-not-allowed",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "resp_01HXYZ"),
        ("note", "Provider returned chatcmpl-abc123"),
    ],
)
def test_live_run_record_rejects_response_ids_in_direct_text(field: str, value: str) -> None:
    record = {"run_id": "run-1", "profile_id": "student_profile_01"}
    record[field] = value

    with pytest.raises(ValidationError):
        LiveRunRecord(**record)


def test_live_run_record_rejects_response_ids_in_nested_message_content() -> None:
    with pytest.raises(ValidationError):
        LiveRunRecord(
            run_id="run-1",
            profile_id="student_profile_01",
            messages=[
                {
                    "role": "assistant",
                    "content": "The provider returned resp_01HXYZ.",
                }
            ],
        )


def test_profile_to_confirmed_facts_excludes_name() -> None:
    facts = profile_to_confirmed_facts(
        {
            "name": "Synthetic Name",
            "degree": "Bachelor",
            "target_roles": ["AI Intern"],
        },
        "student_profile_01",
    )

    assert [fact.field for fact in facts] == ["education", "target_role"]


def test_export_outcome_records_a_blocked_draft() -> None:
    assert export_outcome(SessionState.CV_DRAFT) == "blocked"


def test_recorder_preserves_entry_provenance_warnings_and_review_trace() -> None:
    entry = ResumeEntry(
        entry_id="resume-entry-project", kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="Python API", fact_ids=["fact-project"]),
        source_fact_ids=["fact-project"], status=ResumeEntryStatus.APPROVED,
    )
    session = Session(
        session_id="audit-session", resume_entries=[entry],
        resume_entry_validation_issues=[ResumeEntryValidationIssue(
            entry_id=entry.entry_id, severity="warning", code="wording",
            message="Review the project wording.",
        )],
        trace=[
            TraceEvent(event_type=event, summary=event, details={"entry_id": entry.entry_id})
            for event in (
                "resume_entries_proposed", "resume_entry_updated", "resume_entry_approved"
            )
        ],
    )
    record = session_to_live_run_record(run_id="audit", profile_id="synthetic", session=session)
    audit = record.model_dump(mode="json")
    assert audit["resume_entries"][0]["source_fact_ids"] == ["fact-project"]
    assert audit["resume_entries"][0]["status"] == "approved"
    assert audit["resume_entry_validation_issues"][0]["code"] == "wording"
    assert [event["event_type"] for event in audit["resume_entry_trace"]] == [
        "resume_entries_proposed", "resume_entry_updated", "resume_entry_approved",
    ]


def test_recorder_rejects_response_ids_in_entry_text() -> None:
    session = Session(session_id="audit-session", resume_entries=[ResumeEntry(
        kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="Provider resp_secret", fact_ids=["fact-project"]),
        source_fact_ids=["fact-project"],
    )])
    with pytest.raises(ValidationError, match="keys or response IDs"):
        session_to_live_run_record(run_id="audit", profile_id="synthetic", session=session)


def test_profile_to_confirmed_facts_converts_all_searchable_categories() -> None:
    facts = profile_to_confirmed_facts(
        {
            "degree": "Bachelor",
            "technical_skills": ["Python", "SQL"],
            "projects": [{"title": "Evidence project", "technologies": ["Python"]}],
            "experience": [{"role": "Support assistant"}],
            "target_roles": ["AI Intern", "Software Intern"],
        },
        "student_profile_01",
    )

    assert [fact.field for fact in facts] == [
        "education",
        "skills",
        "project",
        "experience",
        "target_role",
    ]
    assert [fact.value for fact in facts] == [
        "Bachelor",
        "Python, SQL",
        '[{"technologies":["Python"],"title":"Evidence project"}]',
        '[{"role":"Support assistant"}]',
        "AI Intern",
    ]
    assert all(fact.status.value == "confirmed" for fact in facts)
    assert all(fact.source.source_type.value == "imported_test_profile" for fact in facts)
    assert all(fact.source.reference == "student_profile_01" for fact in facts)


def test_session_recorder_keeps_top_three_and_blocking_validation() -> None:
    session = Session(
        session_id="session-private",
        state=SessionState.CV_DRAFT,
        retrieval_results=[
            RetrievalResult(
                document_id=f"job-{index}",
                title=f"Job {index}",
                score=1.0 / index,
                score_breakdown=RetrievalScoreBreakdown(
                    semantic_score=1.0 / index,
                    project_score=0.0,
                    skill_score=0.0,
                    target_role_score=0.0,
                    education_score=0.0,
                    experience_score=0.0,
                    evidence_score=0.0,
                    final_score=1.0 / index,
                ),
                excerpt=f"Exact excerpt {index}.",
            )
            for index in range(1, 5)
        ],
        selected_job_id="job-1",
        validation_issues=[ValidationIssue(code="not_entailed", message="Unsupported claim.")],
    )

    record = session_to_live_run_record(
        run_id="supplied-five-student-profile-01",
        profile_id="student_profile_01",
        session=session,
        transitions=[LiveTransition(from_state="collecting_profile", to_state="profile_confirmed")],
    )

    assert [item.document_id for item in record.retrieval_results] == [
        "job-1",
        "job-2",
        "job-3",
    ]
    assert [item.score for item in record.retrieval_results] == [1.0, 0.5, 1 / 3]
    assert [item.excerpt for item in record.retrieval_results] == [
        "Exact excerpt 1.",
        "Exact excerpt 2.",
        "Exact excerpt 3.",
    ]
    assert record.transitions[0].to_state == "profile_confirmed"
    assert record.cv_results[0].selected_job_id == "job-1"
    assert record.cv_results[0].validation_issues[0].code == "not_entailed"
    assert record.cv_results[0].export_outcome == "blocked"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_runner_accepts_each_explicit_scenario(scenario: str, tmp_path: Path) -> None:
    class StopAfterManifest(RuntimeError):
        pass

    def services_factory() -> object:
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["scenario"] == scenario
        assert re.fullmatch(
            rf"\d{{4}}-\d{{2}}-\d{{2}}-\d{{6}}\d{{6}}-{re.escape(scenario)}\.json",
            manifest["artifacts"][0],
        )
        raise StopAfterManifest

    with pytest.raises(StopAfterManifest):
        main(
            ["--scenario", scenario, "--output-dir", str(tmp_path)],
            services_factory=services_factory,
        )


class OfflineEvaluationProvider:
    def __init__(self, turns: list[ProviderTurn] | None = None) -> None:
        self.turns = list(turns or [])

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] for _text in texts]

    def respond(
        self,
        *,
        input_items: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ProviderTurn:
        del input_items, tools
        return self.turns.pop(0)

    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        return [
            ResumeEntry(
                entry_id=f"resume-entry-{fact.fact_id}",
                kind=ResumeEntryKind(fact.field),
                heading=ResumeText(text=fact.value, fact_ids=[fact.fact_id]),
                source_fact_ids=[fact.fact_id],
            )
            for fact in confirmed_facts
            if fact.field in {"education", "project", "experience"}
        ]

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]:
        del entries, confirmed_facts
        return []

    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument:
        del contact_facts
        entry = approved_entries[0]
        return CVDocument(
            target_job_id=job.document_id,
            headline=entry.heading.text,
            headline_fact_ids=entry.heading.fact_ids,
        )

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        del cv, confirmed_facts
        return []


def offline_services(
    turns: list[ProviderTurn] | None = None,
    *,
    provider: OfflineEvaluationProvider | None = None,
) -> ApplicationServices:
    selected_provider = provider or OfflineEvaluationProvider(turns)
    workflow = SessionWorkflow()
    jobs = JobRepository.load(JobRepository.default_data_path())
    return ApplicationServices(
        workflow=workflow,
        jobs=jobs,
        retrieval=RetrievalService(jobs, selected_provider),
        cv=CVService(workflow, selected_provider),
        resume_entries=ResumeEntryService(workflow, selected_provider),
        agent_provider=selected_provider,
    )


def scenario_artifact_path(output_dir: Path) -> Path:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    return output_dir / manifest["artifacts"][0]


def test_unseen_scenario_runs_the_real_workflow_to_export(tmp_path: Path) -> None:
    result = main(
        ["--scenario", "unseen", "--output-dir", str(tmp_path)],
        services_factory=offline_services,
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    run = artifact["runs"][0]
    assert result == 0
    assert artifact["scenario"] == "unseen"
    assert run["profile_id"] == "unseen_profile_01"
    assert [transition["to_state"] for transition in run["transitions"]][:4] == [
        "profile_confirmed", "resume_entries_review", "resume_entries_approved", "jobs_retrieved",
    ]
    assert run["resume_entries"]
    assert all(entry["status"] == "approved" for entry in run["resume_entries"])
    assert len(run["retrieval_results"]) == 3
    assert run["transitions"][-1]["to_state"] == "pdf_exported"
    assert run["cv_results"][0]["export_outcome"] == "exported"


def test_two_job_comparison_uses_two_currently_retrieved_jobs(tmp_path: Path) -> None:
    result = main(
        ["--scenario", "two-job-comparison", "--output-dir", str(tmp_path)],
        services_factory=offline_services,
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    run = artifact["runs"][0]
    retrieved_ids = [item["document_id"] for item in run["retrieval_results"]]
    selected_ids = [item["selected_job_id"] for item in run["cv_results"]]

    assert result == 0
    assert len(selected_ids) == 2
    assert selected_ids == retrieved_ids[:2]
    assert len(set(selected_ids)) == 2
    assert all(item["export_outcome"] == "exported" for item in run["cv_results"])


@pytest.mark.parametrize(
    ("scenario", "run_count"), [("supplied-five", 5), ("session-isolation", 2)]
)
def test_imported_profiles_keep_approved_entry_sources_in_their_own_session(
    scenario: str, run_count: int, tmp_path: Path,
) -> None:
    result = main(
        ["--scenario", scenario, "--output-dir", str(tmp_path)],
        services_factory=offline_services,
    )
    runs = json.loads(scenario_artifact_path(tmp_path).read_text())["runs"]
    assert result == 0
    assert len(runs) == run_count
    for run in runs:
        assert run["cv_results"][0]["export_outcome"] == "exported"
        assert run["resume_entries"]
        for entry in run["resume_entries"]:
            assert entry["status"] == "approved"
            assert all(
                fact_id.startswith(f"fact-{run['profile_id']}-")
                for fact_id in entry["source_fact_ids"]
            )


def test_rejected_resume_approval_records_failure_before_retrieval(tmp_path: Path) -> None:
    class RejectingProvider(OfflineEvaluationProvider):
        def validate_resume_entries(self, entries, confirmed_facts):
            return [ResumeEntryValidationIssue(
                entry_id=entries[0].entry_id, code="not_entailed", message="Unsupported entry.",
            )]

    result = main(
        ["--scenario", "unseen", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(provider=RejectingProvider()),
    )
    run = json.loads(scenario_artifact_path(tmp_path).read_text())["runs"][0]
    assert result == 1
    assert "ResumeEntryEvidenceError" in run["failure"]
    assert run["retrieval_results"] == []
    assert run["cv_results"] == []
    assert [item["to_state"] for item in run["transitions"]] == [
        "profile_confirmed", "resume_entries_review",
    ]


def test_complete_agent_preserves_full_message_and_flags_a_question(
    tmp_path: Path,
) -> None:
    provider_turns = [ProviderTurn(message="What is your target role?")]

    result = main(
        ["--scenario", "complete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(provider_turns),
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    run = artifact["runs"][0]
    supplied = json.loads(
        (
            Path(__file__).parents[2]
            / "docs/evidence/04_System_Tests/test_profiles/unseen_profile_01.json"
        ).read_text(encoding="utf-8")
    )
    assert result == 1
    assert json.loads(run["messages"][0]["content"]) == supplied
    assert run["messages"][1] == {
        "role": "assistant",
        "content": "What is your target role?",
    }
    assert run["failure"] == "Complete profile received a follow-up question; review required."


def test_incomplete_agent_retains_actual_questions_and_factual_replies(
    tmp_path: Path,
) -> None:
    provider_turns = [
        ProviderTurn(message="Which security role are you targeting?"),
        ProviderTurn(message="What project best demonstrates your skills?"),
        ProviderTurn(message="Thanks, I have recorded those supplied facts."),
    ]

    result = main(
        ["--scenario", "incomplete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(provider_turns),
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    messages = artifact["runs"][0]["messages"]
    assert result == 0
    assert messages[1]["content"] == "Which security role are you targeting?"
    assert messages[2]["content"] == "My target role is Cybersecurity Intern."
    assert messages[3]["content"] == "What project best demonstrates your skills?"
    assert "Network Monitoring Exercise" in messages[4]["content"]
    assert messages[5]["content"] == "Thanks, I have recorded those supplied facts."


def test_incomplete_agent_answers_contact_question_without_inventing_details() -> None:
    profile = {
        "target_roles": ["Cybersecurity Intern"],
        "projects": [{"title": "Network Monitoring Exercise"}],
    }

    reply = RUNNER._factual_reply(
        profile,
        "What email address or other contact details should the CV use?",
        1,
    )

    assert reply == "No contact details are supplied in this synthetic profile."


@pytest.mark.parametrize(
    "question",
    [
        "What name should appear on your CV?",
        "What name and contact details would you like included on your CV?",
    ],
)
def test_incomplete_agent_answers_supplied_name_instead_of_target_role(question: str) -> None:
    reply = RUNNER._factual_reply(
        {"name": "Noah Williams", "target_roles": ["Cybersecurity Intern"]}, question, 1
    )
    assert "Noah Williams" in reply
    assert "Cybersecurity Intern" not in reply
    if "contact" in question:
        assert "No contact details are supplied" in reply


@pytest.mark.parametrize("repeat_at", [1, 2])
def test_incomplete_agent_flags_repeated_question_including_final_turn(
    tmp_path: Path, repeat_at: int
) -> None:
    questions = [
        "What name should appear on your CV?",
        "Which security role are you targeting?",
        "What project best demonstrates your skills?",
    ]
    questions[repeat_at] = questions[0]
    result = main(
        ["--scenario", "incomplete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services([ProviderTurn(message=q) for q in questions]),
    )
    artifact = json.loads(scenario_artifact_path(tmp_path).read_text())
    assert result == 1
    assert "repeated" in artifact["runs"][0]["failure"].lower()


def test_incomplete_agent_accepts_imperative_request_as_follow_up(tmp_path: Path) -> None:
    turns = [
        ProviderTurn(message="Which technical direction would you like to target first?"),
        ProviderTurn(
            message=(
                "Please provide your full name and the best email address "
                "and phone number to include on your CV."
            )
        ),
        ProviderTurn(message="Your draft is ready. Please confirm that it is correct."),
    ]
    result = main(
        ["--scenario", "incomplete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(turns),
    )
    artifact = json.loads(scenario_artifact_path(tmp_path).read_text())
    assert result == 0
    assert "My supplied name is" in artifact["runs"][0]["messages"][4]["content"]


def test_complete_agent_flags_imperative_request(tmp_path: Path) -> None:
    result = main(
        ["--scenario", "complete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(
            [ProviderTurn(message="Please provide your full name.")]
        ),
    )
    assert result == 1


def test_session_isolation_leak_is_a_failed_scenario(tmp_path: Path) -> None:
    class LeakingProvider(OfflineEvaluationProvider):
        def validate_claims(
            self, cv: CVDocument, confirmed_facts: list[Fact]
        ) -> list[ValidationIssue]:
            # Raw facts belong to the evidence validator, not the CV content provider.
            confirmed_facts[0].source.reference = "foreign_profile"
            return super().validate_claims(cv, confirmed_facts)

    result = main(
        ["--scenario", "session-isolation", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(provider=LeakingProvider()),
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    assert result == 1
    assert all(run["failure"] is not None for run in artifact["runs"])
    assert all("isolation" in run["failure"].lower() for run in artifact["runs"])


@pytest.mark.parametrize("scenario", ["complete-agent", "incomplete-agent"])
def test_agent_step_limit_is_preserved_in_an_artifact(scenario: str, tmp_path: Path) -> None:
    turns = [
        ProviderTurn(
            tool_calls=[
                ToolCall(
                    call_id=f"call-{index}",
                    name="update_profile",
                    arguments={"facts": [{"field": f"field-{index}", "value": f"value-{index}"}]},
                )
            ]
        )
        for index in range(7)
    ]

    result = main(
        ["--scenario", scenario, "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(turns),
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    run = artifact["runs"][0]
    assert result == 1
    assert run["failure"] == (
        "AgentStepLimitError: The agent reached its six tool-step safety limit."
    )
    assert run["messages"][0]["role"] == "user"


def test_agent_tool_call_records_profile_review_transition(tmp_path: Path) -> None:
    turns = [
        ProviderTurn(
            tool_calls=[
                ToolCall(
                    call_id="call-1",
                    name="update_profile",
                    arguments={"facts": [{"field": "skills", "value": "Python and SQL"}]},
                )
            ]
        ),
        ProviderTurn(message="I recorded the supplied skills for review."),
    ]

    result = main(
        ["--scenario", "complete-agent", "--output-dir", str(tmp_path)],
        services_factory=lambda: offline_services(turns),
    )

    artifact = json.loads(scenario_artifact_path(tmp_path).read_text(encoding="utf-8"))
    assert result == 0
    assert artifact["runs"][0]["transitions"] == [
        {"from_state": "collecting_profile", "to_state": "profile_review"}
    ]
