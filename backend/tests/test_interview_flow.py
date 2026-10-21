"""Tests for the A3 interview flow (question plan, progression, limits, lifecycle, turns)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.interview_models import (
    InterviewConfig,
    InterviewContextSnapshot,
    InterviewJob,
    PlannedQuestion,
    QuestionPlanProposal,
)
from app.domain.models import (
    CVClaim,
    CVDocument,
    Fact,
    Job,
    ResumeEntry,
    ResumeEntryKind,
    ResumeEntryValidationIssue,
    ResumeText,
    ValidationIssue,
)
from app.domain.workflow import SessionWorkflow
from app.main import ApplicationServices, create_app
from app.providers.base import ProviderTurn
from app.providers.fake import ScriptedProvider
from app.providers.openai_interview_planner import OpenAIQuestionPlanner
from app.services.cv import CVService
from app.services.interview_flow import InterviewFlowService
from app.services.question_planner import (
    TemplateQuestionPlanner,
    job_requirements,
    locate_excerpt,
    validate_plan,
)
from app.services.resume_entries import ResumeEntryService
from app.services.retrieval import JobRepository, RetrievalService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FlatEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class EchoProvider:
    """Turns education/project/experience/skills facts into approved-ready entries."""

    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        kinds = {"education", "project", "experience", "skills"}
        return [
            ResumeEntry(
                kind=ResumeEntryKind(fact.field),
                heading=ResumeText(text=fact.value, fact_ids=[fact.fact_id]),
                source_fact_ids=[fact.fact_id],
            )
            for fact in confirmed_facts
            if fact.field in kinds
        ]

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]:
        return []

    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument:
        first = approved_entries[0]
        return CVDocument(
            target_job_id=job.document_id,
            headline=first.heading.text,
            headline_fact_ids=first.heading.fact_ids,
            claims=[CVClaim(text=first.heading.text, fact_ids=first.heading.fact_ids)],
        )

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        return []


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


FACTS = [
    {"field": "name", "value": "Maya Chen"},
    {"field": "education", "value": "Bachelor of Computing Science at UTS"},
    {"field": "skills", "value": "Python, SQL, REST APIs, pytest"},
    {"field": "project", "value": "Team Course Planner: built a Python REST API with tests"},
    {"field": "experience", "value": "Customer Service Assistant at a retail store"},
    {"field": "target_role", "value": "Graduate Software Engineer"},
]

PASTED_JOB = {
    "source": "pasted_job",
    "title": "Junior Backend Developer",
    "description": (
        "About the role: Join a small team building internal tools. "
        "Requirements: experience with Python web frameworks; writing automated tests; "
        "working with SQL databases; clear written communication."
    ),
}


def build(
    planner: Any = None, clock: Clock | None = None
) -> tuple[TestClient, ApplicationServices]:
    workflow = SessionWorkflow()
    jobs = JobRepository.load(JobRepository.default_data_path())
    services = ApplicationServices(
        workflow=workflow,
        jobs=jobs,
        retrieval=RetrievalService(jobs, FlatEmbedder()),
        cv=CVService(workflow, EchoProvider()),
        resume_entries=ResumeEntryService(workflow, EchoProvider()),
        agent_provider=ScriptedProvider([ProviderTurn(message="ok")]),
        question_planner=planner,
    )
    if clock is not None:
        services.interviews = InterviewFlowService(
            workflow, jobs, planner or TemplateQuestionPlanner(), clock=clock
        )
    return TestClient(create_app(services)), services


def ready_session(client: TestClient, approve: bool = True) -> str:
    session_id = client.post("/api/sessions").json()["session_id"]
    base = f"/api/sessions/{session_id}"
    assert client.put(f"{base}/profile", json={"facts": FACTS}).status_code == 200
    assert client.post(f"{base}/profile/confirm").status_code == 200
    proposed = client.post(f"{base}/resume-entries/propose").json()
    if approve:
        for entry in proposed["resume_entries"]:
            response = client.post(f"{base}/resume-entries/{entry['entry_id']}/approve")
            assert response.status_code == 200
    return base


def create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "request_id": f"create-{uuid4()}",
        "cv_id": None,
        "job": {"source": "supplied_job", "document_id": "graduate_ai_engineer"},
        "config": {
            "interview_type": "mixed",
            "duration_minutes": 10,
            "main_question_count": 4,
            "max_follow_ups_per_question": 1,
            "language": "en",
        },
        "consent": {"send_audio_to_provider": True, "retain_transcript_for_feedback": True},
    }
    body.update(overrides)
    return body


def make_interview(client: TestClient, base: str, **overrides: Any) -> dict[str, Any]:
    response = client.post(f"{base}/interviews", json=create_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def start(client: TestClient, base: str, interview: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"{base}/interviews/{interview['interview_id']}/start",
        json={"request_id": f"start-{uuid4()}", "expected_flow_revision": 0},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TurnWriter:
    """Mimics the voice adapter: registers turns in conversation order."""

    def __init__(self, client: TestClient, base: str, interview_id: str) -> None:
        self.client = client
        self.url = f"{base}/interviews/{interview_id}/turns"
        self.last_turn_id: str | None = None
        self.connection_id = "connection-test"

    def send(
        self,
        question_id: str,
        speaker: str,
        text: str,
        *,
        status: str = "final",
        version: int = 1,
        turn_id: str | None = None,
        previous: str | None | object = ...,
        event_id: str | None = None,
    ) -> Any:
        new_turn = turn_id is None
        turn_id = turn_id or f"turn-{uuid4()}"
        prev = self.last_turn_id if previous is ... else previous
        body = {
            "event_id": event_id or f"event-{uuid4()}",
            "connection_id": self.connection_id,
            "previous_turn_id": prev,
            "turn": {
                "turn_id": turn_id,
                "question_id": question_id,
                "speaker": speaker,
                "input_mode": "live_voice",
                "transcript_version": version,
                "transcript_status": status,
                "text": text,
                "delivery_status": "complete" if speaker == "interviewer" else "not_applicable",
                "timing": {
                    "clock_id": "audio-1",
                    "start_ms": 1000,
                    "end_ms": 4000,
                    "source": "provider_vad",
                },
            },
        }
        response = self.client.post(self.url, json=body)
        if new_turn and response.status_code == 200:
            self.last_turn_id = turn_id
        response.turn_id = turn_id  # type: ignore[attr-defined]
        response.body = body  # type: ignore[attr-defined]
        return response

    def answer(self, question: dict[str, Any], text: str) -> str:
        asked = self.send(question["question_id"], "interviewer", question["text"])
        assert asked.status_code == 200
        response = self.send(question["question_id"], "candidate", text)
        assert response.status_code == 200, response.text
        return response.turn_id  # type: ignore[no-any-return]


def next_step(
    client: TestClient,
    base: str,
    interview_id: str,
    revision: int,
    question_id: str,
    turn_ids: list[str],
    proposal: dict[str, str] | None = None,
    request_id: str | None = None,
) -> Any:
    return client.post(
        f"{base}/interviews/{interview_id}/next-step",
        json={
            "request_id": request_id or f"step-{uuid4()}",
            "expected_flow_revision": revision,
            "answered_question_id": question_id,
            "answer_turn_ids": turn_ids,
            "follow_up_proposal": proposal,
        },
    )


# ---------------------------------------------------------------------------
# Question planning
# ---------------------------------------------------------------------------


def snapshot(interview_type: str = "mixed", count: int = 4, description: str | None = None) -> Any:
    fact = Fact(
        fact_id="fact-project",
        field="project",
        value="Team Course Planner: built a Python REST API",
        status="confirmed",
        source={"source_type": "user_message", "reference": "m1"},
    )
    entry = ResumeEntry(
        entry_id="entry-project",
        kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="Team Course Planner", fact_ids=["fact-project"]),
        bullets=[ResumeText(text="Built a Python REST API with tests", fact_ids=["fact-project"])],
        source_fact_ids=["fact-project"],
        status="approved",
    )
    return InterviewContextSnapshot(
        confirmed_facts=[fact],
        approved_entries=[entry],
        cv=None,
        job=InterviewJob(
            source="pasted_job",
            document_id=None,
            title="Backend Developer",
            description=description or PASTED_JOB["description"],
        ),
        config=InterviewConfig(interview_type=interview_type, main_question_count=count),
    )


@pytest.mark.parametrize("interview_type", ["behavioural", "technical", "mixed"])
@pytest.mark.parametrize("count", [3, 4, 6])
def test_template_planner_always_produces_a_valid_plan(interview_type: str, count: int) -> None:
    context = snapshot(interview_type, count)
    result = validate_plan(context, TemplateQuestionPlanner().plan_questions(context))
    assert result.ok, result.problems
    assert len(result.questions) == count
    for question in result.questions:
        if question.job_requirement_excerpt is not None:
            assert question.job_requirement_excerpt in context.job.description


def test_template_planner_handles_unstructured_pasted_job() -> None:
    context = snapshot("technical", 6, description="We need someone who can build dashboards.")
    result = validate_plan(context, TemplateQuestionPlanner().plan_questions(context))
    assert result.ok, result.problems


def test_job_requirements_are_exact_substrings() -> None:
    for job in JobRepository.load(JobRepository.default_data_path()):
        for item in job_requirements(job.description):
            assert item in job.description


def test_validate_plan_rejects_unknown_references_and_wrong_categories() -> None:
    context = snapshot("behavioural", 3)
    planned = [
        PlannedQuestion(
            category="behavioural", text="Q1?", rationale="r", fact_ids=["fact-invented"]
        ),
        PlannedQuestion(category="technical", text="Q2?", rationale="r"),
        PlannedQuestion(
            category="behavioural", text="Q3?", rationale="r", resume_entry_ids=["entry-x"]
        ),
    ]
    problems = " ".join(validate_plan(context, planned).problems)
    assert "fact_ids" in problems
    assert "resume_entry_ids" in problems
    assert "only contain behavioural" in problems


def test_validate_plan_repairs_or_drops_job_excerpts() -> None:
    context = snapshot("technical", 3)
    planned = [
        PlannedQuestion(
            category="technical",
            text=f"Question {index}?",
            rationale="r",
            job_requirement_excerpt=excerpt,
        )
        for index, excerpt in enumerate(
            ["WRITING  automated tests", "a paraphrase that is not in the job", None]
        )
    ]
    result = validate_plan(context, planned)
    assert result.ok
    assert result.questions[0].job_requirement_excerpt == "writing automated tests"
    assert result.questions[1].job_requirement_excerpt is None
    assert locate_excerpt('"SQL databases"', context.job.description) == "SQL databases"


class FakeResponses:
    def __init__(self, outputs: list[Any]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        if callable(output):
            output = output(json.loads(kwargs["input"]))
        if isinstance(output, Exception):
            raise output
        return type("Response", (), {"output_parsed": output})()


class FakeClient:
    def __init__(self, outputs: list[Any]) -> None:
        self.responses = FakeResponses(outputs)


def test_openai_planner_retries_once_with_validation_problems() -> None:
    bad = QuestionPlanProposal(
        questions=[PlannedQuestion(category="behavioural", text="Only one?", rationale="r")]
    )
    def good(payload: dict[str, Any]) -> QuestionPlanProposal:
        entry = next(
            e for e in payload["approved_resume_entries"] if e["kind"] == "project"
        )
        requirement = payload["target_job"]["description"].split("Requirements: ")[1][:40]
        return QuestionPlanProposal(
            questions=[
                PlannedQuestion(category="behavioural", text="Why this role?", rationale="r"),
                PlannedQuestion(
                    category="technical",
                    text="How would you meet this requirement?",
                    rationale="r",
                    job_requirement_excerpt=requirement,
                ),
                PlannedQuestion(
                    category="behavioural",
                    text="Tell me about your project.",
                    rationale="r",
                    fact_ids=entry["fact_ids"],
                    resume_entry_ids=[entry["entry_id"]],
                ),
            ]
        )

    fake = FakeClient([bad, good])
    client, _ = build(planner=OpenAIQuestionPlanner(model="test-model", client=fake))
    base = ready_session(client)
    interview = make_interview(client, base, config={"main_question_count": 3})
    assert [q["text"] for q in interview["questions"]][0] == "Why this role?"
    assert interview["questions"][1]["job_requirement_excerpt"]
    assert interview["questions"][2]["resume_entry_ids"]
    assert len(fake.responses.calls) == 2
    second_input = json.loads(fake.responses.calls[1]["input"])
    assert second_input["problems_from_previous_attempt"]
    first_input = json.loads(fake.responses.calls[0]["input"])
    assert first_input["target_job"]["title"] == "Graduate AI Engineer"
    assert all(f["fact_id"].startswith("fact-") for f in first_input["confirmed_facts"])


def test_planner_failure_is_a_recoverable_provider_error() -> None:
    fake = FakeClient([RuntimeError("network down")])
    client, _ = build(planner=OpenAIQuestionPlanner(model="test-model", client=fake))
    base = ready_session(client)
    response = client.post(f"{base}/interviews", json=create_body())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_unusable_plan_after_retries_is_503_and_no_interview_is_stored() -> None:
    bad = QuestionPlanProposal(questions=[])
    fake = FakeClient([bad, bad])
    client, services = build(planner=OpenAIQuestionPlanner(model="test-model", client=fake))
    base = ready_session(client)
    assert client.post(f"{base}/interviews", json=create_body()).status_code == 503
    assert services.interviews._records == {}


# ---------------------------------------------------------------------------
# Creation and frozen context
# ---------------------------------------------------------------------------


def test_create_requires_confirmed_profile_and_approved_entries() -> None:
    client, _ = build()
    base = ready_session(client, approve=False)
    response = client.post(f"{base}/interviews", json=create_body())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interview_not_ready"


def test_create_with_supplied_job_returns_ready_interview() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    assert interview["phase"] == "ready"
    assert interview["flow_revision"] == 0
    assert interview["job"]["document_id"] == "graduate_ai_engineer"
    assert len(interview["context_hash"]) == 64
    assert len(interview["questions"]) == 4
    assert {q["status"] for q in interview["questions"]} == {"planned"}
    assert {q["category"] for q in interview["questions"]} == {"behavioural", "technical"}
    assert interview["current_question_id"] is None
    fetched = client.get(f"{base}/interviews/{interview['interview_id']}")
    assert fetched.json() == interview


def test_create_with_pasted_job_and_validation() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base, job=PASTED_JOB)
    assert interview["job"]["source"] == "pasted_job"
    assert interview["job"]["document_id"] is None
    excerpts = [q["job_requirement_excerpt"] for q in interview["questions"]]
    assert any(excerpt for excerpt in excerpts)
    for excerpt in filter(None, excerpts):
        assert excerpt in PASTED_JOB["description"]

    too_long = dict(PASTED_JOB, title="x" * 201)
    assert client.post(f"{base}/interviews", json=create_body(job=too_long)).status_code == 422
    mixed = dict(PASTED_JOB, document_id="graduate_ai_engineer")
    assert client.post(f"{base}/interviews", json=create_body(job=mixed)).status_code == 422
    bad_config = create_body(config={"main_question_count": 7})
    assert client.post(f"{base}/interviews", json=bad_config).status_code == 422
    unknown = create_body(job={"source": "supplied_job", "document_id": "no_such_job"})
    response = client.post(f"{base}/interviews", json=unknown)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_two_jobs_produce_different_questions_for_the_same_candidate() -> None:
    client, _ = build()
    base = ready_session(client)
    first = make_interview(client, base)
    second = make_interview(
        client, base, job={"source": "supplied_job", "document_id": "computer_vision_engineer"}
    )
    assert [q["text"] for q in first["questions"]] != [q["text"] for q in second["questions"]]
    assert first["context_hash"] != second["context_hash"]


def test_create_is_idempotent_per_request_id() -> None:
    client, _ = build()
    base = ready_session(client)
    body = create_body()
    first = client.post(f"{base}/interviews", json=body).json()
    again = client.post(f"{base}/interviews", json=body).json()
    assert again["interview_id"] == first["interview_id"]
    changed = dict(body, config={"main_question_count": 3})
    response = client.post(f"{base}/interviews", json=changed)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "request_id_conflict"


def test_cv_must_be_current_and_validated() -> None:
    client, _ = build()
    base = ready_session(client)
    client.post(f"{base}/jobs/retrieve")
    assert client.post(f"{base}/jobs/graduate_ai_engineer/select").status_code == 200
    cv = client.post(f"{base}/cvs").json()["cv"]
    draft = client.post(f"{base}/interviews", json=create_body(cv_id=cv["cv_id"]))
    assert draft.status_code == 409
    assert draft.json()["error"]["code"] == "cv_not_validated"
    assert client.post(f"{base}/cvs/{cv['cv_id']}/validate").status_code == 200
    interview = make_interview(client, base, cv_id=cv["cv_id"])
    assert interview["cv_id"] == cv["cv_id"]
    assert interview["cv_content_hash"]


def test_profile_edits_do_not_rewrite_an_existing_interview() -> None:
    client, services = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    session_id = base.rsplit("/", 1)[1]
    client.put(f"{base}/profile", json={"facts": [{"field": "skills", "value": "Rust"}]})
    after = client.get(f"{base}/interviews/{interview['interview_id']}").json()
    assert after == interview
    frozen = services.interviews.get_context(session_id, interview["interview_id"])
    assert any("Python" in fact.value for fact in frozen.confirmed_facts)


def test_foreign_session_cannot_read_an_interview() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    other = ready_session(client)
    response = client.get(f"{other}/interviews/{interview['interview_id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "interview_not_found"


# ---------------------------------------------------------------------------
# Progression
# ---------------------------------------------------------------------------


def test_full_interview_with_follow_up_limit_skip_and_end() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    interview_id = interview["interview_id"]
    started = start(client, base, interview)
    assert started["interview"]["phase"] == "active"
    q1 = started["next_step"]["question"]
    assert q1["status"] == "issued" and q1["kind"] == "main"
    revision = started["next_step"]["flow_revision"]
    writer = TurnWriter(client, base, interview_id)

    # Q1 answered with a follow-up proposal -> follow-up accepted.
    a1 = writer.answer(q1, "I built a Python REST API in a team.")
    proposal = {"text": "How did you test that API?", "rationale": "Answer omitted testing."}
    step = next_step(client, base, interview_id, revision, q1["question_id"], [a1], proposal)
    assert step.status_code == 200, step.text
    follow_up = step.json()["question"]
    assert follow_up["kind"] == "follow_up"
    assert follow_up["parent_question_id"] == q1["question_id"]
    revision = step.json()["flow_revision"]

    # Follow-up answered with another proposal -> limit (1) reached, next main question.
    a2 = writer.answer(follow_up, "We used pytest for the endpoints.")
    step = next_step(
        client, base, interview_id, revision, follow_up["question_id"], [a2],
        {"text": "Which tests failed most?", "rationale": "More depth."},
    )
    q2 = step.json()["question"]
    assert q2["kind"] == "main" and q2["question_id"] != q1["question_id"]
    revision = step.json()["flow_revision"]

    # Skip Q2.
    skipped = client.post(
        f"{base}/interviews/{interview_id}/skip",
        json={"request_id": "skip-1", "expected_flow_revision": revision,
              "question_id": q2["question_id"]},
    )
    assert skipped.status_code == 200
    q3 = skipped.json()["question"]
    revision = skipped.json()["flow_revision"]

    # Answer Q3 but end before calling next-step: the last answer is still submitted.
    writer.answer(q3, "I would start by reproducing the problem.")
    ended = client.post(
        f"{base}/interviews/{interview_id}/end",
        json={"request_id": "end-1", "expected_flow_revision": revision},
    )
    assert ended.status_code == 200, ended.text
    final = ended.json()
    assert final["phase"] == "completed"
    assert final["end_reason"] == "user_finished"
    statuses = {q["question_id"]: q["status"] for q in final["questions"]}
    assert statuses[q1["question_id"]] == "answered"
    assert statuses[follow_up["question_id"]] == "answered"
    assert statuses[q2["question_id"]] == "skipped"
    assert statuses[q3["question_id"]] == "answered"
    assert sum(1 for q in final["questions"] if q["kind"] == "follow_up") == 1
    order = [q["question_id"] for q in final["questions"]]
    assert order.index(follow_up["question_id"]) == order.index(q1["question_id"]) + 1


def test_all_questions_answered_finishes_with_questions_complete() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(
        client, base, config={"main_question_count": 3, "max_follow_ups_per_question": 0}
    )
    started = start(client, base, interview)
    writer = TurnWriter(client, base, interview["interview_id"])
    question = started["next_step"]["question"]
    revision = started["next_step"]["flow_revision"]
    for _ in range(3):
        answer = writer.answer(question, "An answer.")
        step = next_step(
            client, base, interview["interview_id"], revision, question["question_id"], [answer],
            {"text": "Ignored follow-up?", "rationale": "limit is zero"},
        ).json()
        revision = step["flow_revision"]
        if step["action"] == "finish":
            break
        question = step["question"]
    assert step == {"action": "finish", "reason": "questions_complete", "flow_revision": revision}
    final = client.get(f"{base}/interviews/{interview['interview_id']}").json()
    assert final["phase"] == "completed" and final["end_reason"] == "questions_complete"


def test_next_step_waits_for_pending_transcripts_and_rejects_failed_ones() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    started = start(client, base, interview)
    q1 = started["next_step"]["question"]
    writer = TurnWriter(client, base, interview["interview_id"])
    writer.send(q1["question_id"], "interviewer", q1["text"])
    pending = writer.send(q1["question_id"], "candidate", "", status="pending")
    request_id = "step-pending"
    response = next_step(
        client, base, interview["interview_id"], 1, q1["question_id"], [pending.turn_id],
        request_id=request_id,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "transcript_pending"
    assert error["details"] == {"retryable": True, "turn_ids": [pending.turn_id]}

    # Partial then final update with the same turn ID; the same request ID then succeeds.
    assert writer.send(
        q1["question_id"], "candidate", "I built", status="partial", version=2,
        turn_id=pending.turn_id, previous=pending.body["previous_turn_id"],
    ).status_code == 200
    assert writer.send(
        q1["question_id"], "candidate", "I built an API.", version=3,
        turn_id=pending.turn_id, previous=pending.body["previous_turn_id"],
    ).status_code == 200
    response = next_step(
        client, base, interview["interview_id"], 1, q1["question_id"], [pending.turn_id],
        request_id=request_id,
    )
    assert response.status_code == 200, response.text
    q2 = response.json()["question"]

    failed = writer.send(q2["question_id"], "candidate", "", status="failed")
    response = next_step(
        client, base, interview["interview_id"], 2, q2["question_id"], [failed.turn_id]
    )
    assert response.json()["error"]["code"] == "transcript_failed"


def test_progression_conflicts_and_idempotent_replay() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    interview_id = interview["interview_id"]
    started = start(client, base, interview)
    q1 = started["next_step"]["question"]
    writer = TurnWriter(client, base, interview_id)
    answer = writer.answer(q1, "My answer.")

    stale = next_step(client, base, interview_id, 0, q1["question_id"], [answer])
    assert stale.json()["error"]["code"] == "flow_revision_conflict"

    first = next_step(client, base, interview_id, 1, q1["question_id"], [answer], request_id="r1")
    replay = next_step(client, base, interview_id, 1, q1["question_id"], [answer], request_id="r1")
    assert replay.status_code == 200 and replay.json() == first.json()

    competing = next_step(client, base, interview_id, 1, q1["question_id"], [answer])
    assert competing.status_code == 409

    q2 = first.json()["question"]
    reused = next_step(client, base, interview_id, 2, q2["question_id"], [answer])
    assert reused.json()["error"]["code"] == "invalid_answer_turn"

    wrong_question = next_step(client, base, interview_id, 2, q1["question_id"], [answer])
    assert wrong_question.json()["error"]["code"] == "question_not_current"

    changed = next_step(client, base, interview_id, 2, q2["question_id"], [answer], request_id="r1")
    assert changed.json()["error"]["code"] == "request_id_conflict"


def test_start_requires_consent_and_ready_phase() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(
        client, base,
        consent={"send_audio_to_provider": True, "retain_transcript_for_feedback": False},
    )
    url = f"{base}/interviews/{interview['interview_id']}/start"
    response = client.post(url, json={"request_id": "s1", "expected_flow_revision": 0})
    assert response.json()["error"]["code"] == "consent_required"

    ok = make_interview(client, base)
    body = {"request_id": "s1", "expected_flow_revision": 0}
    url = f"{base}/interviews/{ok['interview_id']}/start"
    first = client.post(url, json=body)
    assert client.post(url, json=body).json() == first.json()
    again = client.post(url, json={"request_id": "s2", "expected_flow_revision": 1})
    assert again.json()["error"]["code"] == "invalid_interview_phase"


def test_cancel_is_terminal_and_end_requires_active() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    url = f"{base}/interviews/{interview['interview_id']}"
    early_end = client.post(f"{url}/end", json={"request_id": "e", "expected_flow_revision": 0})
    assert early_end.json()["error"]["code"] == "invalid_interview_phase"
    cancelled = client.post(f"{url}/cancel", json={"request_id": "c", "expected_flow_revision": 0})
    assert cancelled.json()["phase"] == "cancelled"
    assert cancelled.json()["end_reason"] == "user_cancelled"
    response = client.post(f"{url}/start", json={"request_id": "s", "expected_flow_revision": 1})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Time limit and finalization
# ---------------------------------------------------------------------------


def test_server_enforces_the_time_limit() -> None:
    clock = Clock()
    client, _ = build(clock=clock)
    base = ready_session(client)
    interview = make_interview(client, base, config={"duration_minutes": 5})
    interview_id = interview["interview_id"]
    started = start(client, base, interview)
    q1 = started["next_step"]["question"]
    writer = TurnWriter(client, base, interview_id)
    answer = writer.answer(q1, "Answer captured before the deadline.")

    clock.advance(minutes=5)
    state = client.get(f"{base}/interviews/{interview_id}").json()
    assert state["phase"] == "completed"
    assert state["end_reason"] == "time_limit"
    assert state["current_question_id"] is None
    assert next(q for q in state["questions"] if q["question_id"] == q1["question_id"])[
        "status"
    ] == "answered"

    step = next_step(client, base, interview_id, 1, q1["question_id"], [answer])
    assert step.status_code == 200
    assert step.json()["action"] == "finish" and step.json()["reason"] == "time_limit"


def test_time_limit_reached_during_next_step_finishes() -> None:
    clock = Clock()
    client, _ = build(clock=clock)
    base = ready_session(client)
    interview = make_interview(client, base, config={"duration_minutes": 5})
    started = start(client, base, interview)
    q1 = started["next_step"]["question"]
    writer = TurnWriter(client, base, interview["interview_id"])
    answer = writer.answer(q1, "Answer.")
    clock.advance(minutes=4, seconds=59)
    step = next_step(client, base, interview["interview_id"], 1, q1["question_id"], [answer])
    assert step.json()["action"] == "ask_question"
    clock.advance(seconds=2)
    state = client.get(f"{base}/interviews/{interview['interview_id']}").json()
    assert state["end_reason"] == "time_limit"


def test_finalization_drains_pending_transcripts_then_marks_them_failed() -> None:
    clock = Clock()
    client, _ = build(clock=clock)
    base = ready_session(client)
    interview = make_interview(client, base)
    interview_id = interview["interview_id"]
    started = start(client, base, interview)
    q1 = started["next_step"]["question"]
    writer = TurnWriter(client, base, interview_id)
    writer.send(q1["question_id"], "interviewer", q1["text"])
    pending = writer.send(q1["question_id"], "candidate", "", status="pending")
    ended = client.post(
        f"{base}/interviews/{interview_id}/end",
        json={"request_id": "end", "expected_flow_revision": 1},
    ).json()
    assert ended["phase"] == "finalizing"

    # A new turn cannot be created while finalizing, but the pending one may finalize.
    late_new = writer.send(q1["question_id"], "candidate", "late new turn")
    assert late_new.status_code == 409
    done = writer.send(
        q1["question_id"], "candidate", "Final words.", version=2, turn_id=pending.turn_id,
        previous=pending.body["previous_turn_id"],
    )
    assert done.status_code == 200
    state = client.get(f"{base}/interviews/{interview_id}").json()
    assert state["phase"] == "completed"
    assert next(q for q in state["questions"] if q["question_id"] == q1["question_id"])[
        "status"
    ] == "answered"

    # Second interview: the transcript never finalizes -> failed after the drain window.
    other = make_interview(client, base)
    started = start(client, base, other)
    q = started["next_step"]["question"]
    writer = TurnWriter(client, base, other["interview_id"])
    writer.send(q["question_id"], "candidate", "", status="pending")
    client.post(
        f"{base}/interviews/{other['interview_id']}/end",
        json={"request_id": "end", "expected_flow_revision": 1},
    )
    clock.advance(seconds=11)
    state = client.get(f"{base}/interviews/{other['interview_id']}").json()
    assert state["phase"] == "completed"
    assert state["turns"][0]["transcript_status"] == "failed"
    assert state["questions"][0]["status"] == "issued"  # never scored as answered


# ---------------------------------------------------------------------------
# Transcript turns
# ---------------------------------------------------------------------------


def test_turn_events_are_ordered_versioned_and_idempotent() -> None:
    client, services = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    interview_id = interview["interview_id"]
    q1 = start(client, base, interview)["next_step"]["question"]
    writer = TurnWriter(client, base, interview_id)

    first = writer.send(q1["question_id"], "interviewer", q1["text"])
    assert first.json()["transcript_revision"] == 1
    replay = client.post(writer.url, json=first.body)
    assert replay.json() == first.json()
    conflicting = dict(first.body, turn=dict(first.body["turn"], text="changed"))
    assert client.post(writer.url, json=conflicting).json()["error"]["code"] == "event_id_conflict"

    no_prev = writer.send(q1["question_id"], "candidate", "x", previous=None)
    assert no_prev.json()["error"]["code"] == "invalid_turn_order"
    missing_prev = writer.send(q1["question_id"], "candidate", "x", previous="turn-unknown")
    assert missing_prev.json()["error"]["code"] == "predecessor_pending"

    answer = writer.send(q1["question_id"], "candidate", "Final text", version=2)
    downgrade = writer.send(
        q1["question_id"], "candidate", "partial", status="partial", version=3,
        turn_id=answer.turn_id, previous=answer.body["previous_turn_id"],
    )
    assert downgrade.json()["error"]["code"] == "transcript_final"
    same_version = writer.send(
        q1["question_id"], "candidate", "different", version=2,
        turn_id=answer.turn_id, previous=answer.body["previous_turn_id"],
    )
    assert same_version.json()["error"]["code"] == "transcript_version_conflict"
    identity = writer.send(
        q1["question_id"], "interviewer", "x", version=4,
        turn_id=answer.turn_id, previous=answer.body["previous_turn_id"],
    )
    assert identity.json()["error"]["code"] == "turn_identity_conflict"

    wrong_question = writer.send("question-other", "candidate", "x")
    assert wrong_question.json()["error"]["code"] == "question_not_current"

    session_id = base.rsplit("/", 1)[1]
    services.interviews.bind_connection(session_id, interview_id)
    stale = writer.send(q1["question_id"], "candidate", "old connection")
    assert stale.json()["error"]["code"] == "stale_connection"

    state = client.get(f"{base}/interviews/{interview_id}").json()
    assert [t["turn_id"] for t in state["turns"]] == [first.turn_id, answer.turn_id]


def test_candidate_and_interviewer_delivery_rules_are_validated() -> None:
    client, _ = build()
    base = ready_session(client)
    interview = make_interview(client, base)
    q1 = start(client, base, interview)["next_step"]["question"]
    writer = TurnWriter(client, base, interview["interview_id"])
    response = writer.send(q1["question_id"], "candidate", "x")
    body = dict(response.body, event_id="event-bad")
    body["turn"] = dict(body["turn"], turn_id="turn-bad", delivery_status="complete")
    body["previous_turn_id"] = response.turn_id
    assert client.post(writer.url, json=body).status_code == 422
    body["turn"] = dict(body["turn"], delivery_status="not_applicable",
                        timing={"clock_id": "a", "start_ms": 10, "end_ms": 5,
                                "source": "provider_vad"})
    assert client.post(writer.url, json=body).status_code == 422
