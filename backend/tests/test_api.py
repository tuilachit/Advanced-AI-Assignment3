import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.domain.models import (
    CVClaim,
    CVDocument,
    Fact,
    Job,
    ResumeEntry,
    ResumeEntryDetail,
    ResumeEntryEdit,
    ResumeEntryKind,
    ResumeEntryValidationIssue,
    ResumeText,
    ValidationIssue,
)
from app.domain.workflow import SessionWorkflow
from app.main import ApplicationServices, create_app
from app.providers.base import (
    AgentModelProvider,
    ProviderProtocolError,
    ProviderTurn,
    ProviderUnavailableError,
    ToolCall,
)
from app.providers.fake import ScriptedCVProvider, ScriptedProvider
from app.providers.unavailable import MissingOpenAIProvider
from app.services.cv import CVService
from app.services.resume_entries import ResumeEntryService
from app.services.retrieval import JobRepository, RetrievalService


class FlatEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


class EvidenceEchoCVProvider:
    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        return [
            ResumeEntry(
                kind=ResumeEntryKind(fact.field),
                heading=ResumeText(text=fact.value, fact_ids=[fact.fact_id]),
                source_fact_ids=[fact.fact_id],
            )
            for fact in confirmed_facts
            if fact.field in {"education", "project"}
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
        evidence = next(
            entry for entry in approved_entries if entry.kind is ResumeEntryKind.PROJECT
        )
        education = next(
            entry for entry in approved_entries if entry.kind is ResumeEntryKind.EDUCATION
        )
        return CVDocument(
            target_job_id=job.document_id,
            headline=education.heading.text,
            headline_fact_ids=education.heading.fact_ids,
            claims=[CVClaim(text=evidence.heading.text, fact_ids=evidence.heading.fact_ids)],
        )

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        del cv, confirmed_facts
        return []


def make_services(agent_provider: AgentModelProvider | None = None) -> ApplicationServices:
    workflow = SessionWorkflow()
    jobs = JobRepository.load(JobRepository.default_data_path())
    cv_service = CVService(workflow, EvidenceEchoCVProvider())
    return ApplicationServices(
        workflow=workflow,
        jobs=jobs,
        retrieval=RetrievalService(jobs, FlatEmbedder()),
        cv=cv_service,
        resume_entries=ResumeEntryService(workflow, EvidenceEchoCVProvider()),
        agent_provider=agent_provider
        or ScriptedProvider(
            [ProviderTurn(message="Tell me about your education, skills, and target role.")]
        ),
    )


def required_facts() -> list[dict[str, str]]:
    return [
        {"field": "name", "value": "Maya Chen"},
        {"field": "education", "value": "Bachelor of Computing Science at UTS"},
        {"field": "skills", "value": "Python, SQL, REST APIs"},
        {"field": "project", "value": "Built a course-planning API with Python"},
        {"field": "target_role", "value": "Software Engineering Intern"},
    ]


@pytest.mark.parametrize(
    ("failure", "expected_code", "message_fragment"),
    [
        ("protocol", "provider_invalid_response", "retry"),
        ("network", "provider_connection_error", "connection"),
        ("timeout", "provider_timeout", "timed out"),
        ("auth", "provider_authentication_error", "key"),
        ("quota", "provider_quota_exhausted", "billing"),
        ("rate", "provider_rate_limited", "shortly"),
        ("access", "provider_access_denied", "access"),
        ("outage", "provider_unavailable", "temporarily"),
    ],
)
def test_provider_failure_reports_safe_actionable_cause(
    failure, expected_code, message_fragment, caplog
) -> None:
    private = "private-profile-and-key-never-log"

    class FailingProvider:
        def respond(self, **kwargs):
            if failure == "protocol":
                raise ProviderProtocolError(private)
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            if failure == "network":
                cause = APIConnectionError(message=private, request=request)
            elif failure == "timeout":
                cause = APITimeoutError(request=request)
            else:
                status_code = {
                    "auth": 401,
                    "quota": 429,
                    "rate": 429,
                    "access": 403,
                    "outage": 503,
                }[failure]
                cause = APIStatusError(
                    private,
                    response=httpx.Response(status_code, request=request),
                    body={
                        "code": "insufficient_quota" if failure == "quota" else private,
                    },
                )
            raise ProviderUnavailableError(private) from cause

    services = make_services(FailingProvider())
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    before = client.get(base).json()
    with caplog.at_level("WARNING", logger="app.main"):
        response = client.post(f"{base}/messages", json={"message": "Help me continue"})
    assert response.status_code in {502, 503}
    assert response.json()["error"]["code"] == expected_code
    assert message_fragment in response.json()["error"]["message"].lower()
    assert client.get(base).json() == before
    assert "Provider failure" in caplog.text
    assert private not in caplog.text
    assert private not in response.text


def test_rich_extraction_can_confirm_review_entries_and_match_without_losing_facts() -> None:
    facts = [fact for fact in required_facts() if fact["field"] != "project"] + [
        {"field": "experience_startup", "value": "Built Python APIs"},
        {"field": "experience_internship", "value": "Built Python data pipelines"},
        {"field": "projects", "value": "Built a Python retrieval assistant"},
        {"field": "research_finance", "value": "Evaluated financial retrieval"},
    ]
    services = make_services(
        ScriptedProvider(
            [
                ProviderTurn(
                    tool_calls=[
                        ToolCall(
                            call_id="extract-rich",
                            name="update_profile",
                            arguments={"facts": facts},
                        )
                    ]
                ),
                ProviderTurn(message="Review the extracted facts, then confirm."),
            ]
        )
    )
    client = TestClient(create_app(services))
    session_id = client.post("/api/sessions").json()["session_id"]
    base = f"/api/sessions/{session_id}"
    extracted = client.post(f"{base}/messages", json={"message": "My rich demo profile"})
    assert extracted.status_code == 200
    before = extracted.json()["session"]["profile"]["facts"]
    confirmed = client.post(f"{base}/profile/confirm")
    assert confirmed.status_code == 200
    assert [f["fact_id"] for f in confirmed.json()["profile"]["facts"]] == [
        f["fact_id"] for f in before
    ]
    entries = [
        ResumeEntry(
            kind=ResumeEntryKind.PROJECT,
            heading=ResumeText(text=f["value"], fact_ids=[f["fact_id"]]),
            source_fact_ids=[f["fact_id"]],
        )
        for f in before
        if f["field"] == "projects"
    ]
    services.resume_entries = ResumeEntryService(
        services.workflow,
        ScriptedCVProvider(
            generated=CVDocument(target_job_id="unused", headline="Unused"),
            proposed_entries=entries,
        ),
    )
    approve_entries(client, base)
    matched = client.post(f"{base}/jobs/retrieve")
    assert matched.status_code == 200
    results = matched.json()["retrieval_results"]
    assert len({r["document_id"] for r in results}) == 3
    assert any(r["score_breakdown"]["experience_score"] > 0 for r in results)
    assert any(r["score_breakdown"]["project_score"] > 0 for r in results)
    assert [f["fact_id"] for f in matched.json()["profile"]["facts"]] == [
        f["fact_id"] for f in before
    ]


def confirmed_session(client: TestClient) -> str:
    session_id = client.post("/api/sessions").json()["session_id"]
    base = f"/api/sessions/{session_id}"
    assert client.put(f"{base}/profile", json={"facts": required_facts()}).status_code == 200
    assert client.post(f"{base}/profile/confirm").status_code == 200
    return base


def approve_entries(client: TestClient, base: str) -> None:
    proposed = client.post(f"{base}/resume-entries/propose")
    assert proposed.status_code == 200
    for entry in proposed.json()["resume_entries"]:
        approved = client.post(f"{base}/resume-entries/{entry['entry_id']}/approve")
        assert approved.status_code == 200


def test_complete_api_workflow_reaches_recorded_pdf_export() -> None:
    client = TestClient(create_app(make_services()))

    created = client.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    updated = client.put(f"/api/sessions/{session_id}/profile", json={"facts": required_facts()})
    assert updated.json()["state"] == "profile_review"

    confirmed = client.post(f"/api/sessions/{session_id}/profile/confirm")
    assert confirmed.json()["state"] == "profile_confirmed"
    assert all(fact["status"] == "confirmed" for fact in confirmed.json()["profile"]["facts"])

    approve_entries(client, f"/api/sessions/{session_id}")
    retrieved = client.post(f"/api/sessions/{session_id}/jobs/retrieve")
    assert retrieved.status_code == 200
    assert retrieved.json()["state"] == "jobs_retrieved"
    assert len(retrieved.json()["retrieval_results"]) == 3
    document_id = retrieved.json()["retrieval_results"][0]["document_id"]

    selected = client.post(f"/api/sessions/{session_id}/jobs/{document_id}/select")
    assert selected.json()["state"] == "job_selected"

    generated = client.post(f"/api/sessions/{session_id}/cvs")
    assert generated.status_code == 201
    cv_id = generated.json()["cv"]["cv_id"]
    assert generated.json()["session"]["state"] == "cv_draft"
    assert generated.json()["session"]["trace"][-1]["event_type"] == "cv_generated"

    validated = client.post(f"/api/sessions/{session_id}/cvs/{cv_id}/validate")
    assert validated.json()["state"] == "cv_validated"
    assert validated.json()["validated_content_hash"]

    exported = client.post(f"/api/sessions/{session_id}/cvs/{cv_id}/export")
    assert exported.json()["state"] == "pdf_exported"

    trace = client.get(f"/api/sessions/{session_id}/trace")
    assert trace.status_code == 200
    assert {event["event_type"] for event in trace.json()["events"]} >= {
        "profile_confirmed",
        "jobs_retrieved",
        "job_selected",
        "cv_generated",
        "cv_validated",
        "pdf_exported",
    }


def test_message_route_returns_agent_response_and_current_session() -> None:
    client = TestClient(create_app(make_services()))
    session_id = client.post("/api/sessions").json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"message": "I am studying computing."},
    )

    assert response.status_code == 200
    assert response.json()["message"].startswith("Tell me about")
    assert response.json()["session"]["session_id"] == session_id


def test_partial_agent_failure_keeps_committed_profile_and_revokes_old_export() -> None:
    provider = ScriptedProvider(
        [
            ProviderTurn(
                tool_calls=[
                    ToolCall(
                        call_id="update-1",
                        name="update_profile",
                        arguments={
                            "facts": [{"field": "project", "value": "Built a new Python chatbot"}]
                        },
                    )
                ]
            ),
            ProviderTurn(message=""),
            ProviderTurn(message="Your new project is saved; please review it."),
        ]
    )
    client = TestClient(create_app(make_services(provider)))
    session_id = client.post("/api/sessions").json()["session_id"]
    base = f"/api/sessions/{session_id}"
    client.put(f"{base}/profile", json={"facts": required_facts()})
    client.post(f"{base}/profile/confirm")
    approve_entries(client, base)
    job_id = client.post(f"{base}/jobs/retrieve").json()["retrieval_results"][0]["document_id"]
    client.post(f"{base}/jobs/{job_id}/select")
    cv_id = client.post(f"{base}/cvs").json()["cv"]["cv_id"]
    assert client.post(f"{base}/cvs/{cv_id}/validate").json()["validated_content_hash"]

    failed = client.post(f"{base}/messages", json={"message": "I built a new Python chatbot"})
    assert failed.status_code == 503
    refreshed = client.get(base).json()
    assert refreshed["cv"] is None
    assert refreshed["validated_content_hash"] is None
    assert refreshed["state"] == "profile_review"
    assert any(
        fact["value"] == "Built a new Python chatbot" for fact in refreshed["profile"]["facts"]
    )
    assert client.post(f"{base}/cvs/{cv_id}/export").status_code == 409
    recovered = client.post(f"{base}/messages", json={"message": "Continue"})
    assert recovered.status_code == 200
    assert recovered.json()["session"]["profile"] == refreshed["profile"]


def test_api_errors_have_a_consistent_safe_envelope() -> None:
    client = TestClient(create_app(make_services()))

    missing = client.get("/api/sessions/not-real")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "session_not_found",
            "message": "The requested session was not found.",
            "details": {},
        }
    }

    session_id = client.post("/api/sessions").json()["session_id"]
    conflict = client.post(f"/api/sessions/{session_id}/jobs/retrieve")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invalid_transition"

    invalid = client.post(f"/api/sessions/{session_id}/messages", json={"message": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "request_validation_error"
    assert "OPENAI_API_KEY" not in str(invalid.json())


def test_openapi_documents_the_runtime_error_envelope() -> None:
    schema = create_app(make_services()).openapi()
    message_responses = schema["paths"]["/api/sessions/{session_id}/messages"]["post"]["responses"]

    assert message_responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorBody"
    }
    assert message_responses["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorBody"
    }
    session_schema = schema["components"]["schemas"]["Session"]
    assert set(session_schema["required"]) == set(session_schema["properties"])


def test_openapi_requires_the_complete_retrieval_score_breakdown() -> None:
    schema = create_app(make_services()).openapi()
    retrieval_schema = schema["components"]["schemas"]["RetrievalResult"]
    assert retrieval_schema["properties"]["score_breakdown"] == {
        "$ref": "#/components/schemas/RetrievalScoreBreakdown"
    }
    assert set(retrieval_schema["required"]) == set(retrieval_schema["properties"])
    score_schema = schema["components"]["schemas"]["RetrievalScoreBreakdown"]
    expected_score_fields = {
        "semantic_score",
        "project_score",
        "skill_score",
        "target_role_score",
        "education_score",
        "experience_score",
        "evidence_score",
        "final_score",
    }
    assert set(score_schema["properties"]) == expected_score_fields
    assert set(score_schema["required"]) == expected_score_fields


def test_cors_allows_only_the_local_frontend_origin() -> None:
    client = TestClient(create_app(make_services()))

    allowed = client.options(
        "/api/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    denied = client.options(
        "/api/sessions",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_api_requires_approved_resume_entry_before_retrieval() -> None:
    client = TestClient(create_app(make_services()))
    base = confirmed_session(client)
    assert client.post(f"{base}/jobs/retrieve").status_code == 409
    proposed = client.post(f"{base}/resume-entries/propose")
    assert proposed.status_code == 200
    assert proposed.json()["state"] == "resume_entries_review"
    assert client.post(f"{base}/jobs/retrieve").status_code == 409
    entry_id = proposed.json()["resume_entries"][0]["entry_id"]
    approved = client.post(f"{base}/resume-entries/{entry_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["state"] == "resume_entries_approved"
    assert client.post(f"{base}/jobs/retrieve").status_code == 200
    duplicate = client.post(f"{base}/resume-entries/{entry_id}/approve")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "invalid_transition"
    deleted = client.delete(f"{base}/resume-entries/{entry_id}")
    assert deleted.status_code == 200
    assert deleted.json()["retrieval_results"] == []
    assert entry_id not in [entry["entry_id"] for entry in deleted.json()["resume_entries"]]
    assert client.post(f"{base}/jobs/retrieve").status_code == 409


def test_api_checks_resume_approval_before_retrieval_provider_availability() -> None:
    services = make_services()
    services.retrieval = RetrievalService(services.jobs, MissingOpenAIProvider())
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    response = client.post(f"{base}/jobs/retrieve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    approve_entries(client, base)
    assert client.post(f"{base}/jobs/retrieve").status_code == 503


def test_api_edits_display_text_and_preserves_server_evidence() -> None:
    services = make_services()
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    session = services.workflow.get_session(base.rsplit("/", 1)[1])
    fact = next(fact for fact in session.profile.facts if fact.field == "project")
    entry = ResumeEntry(
        kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="Course-planning API", fact_ids=[fact.fact_id]),
        organisation_or_context=ResumeText(text="Course project", fact_ids=[fact.fact_id]),
        details=[ResumeEntryDetail(
            label="Technology", value=ResumeText(text="Python", fact_ids=[fact.fact_id])
        )],
        bullets=[ResumeText(text=fact.value, fact_ids=[fact.fact_id])],
        source_fact_ids=[fact.fact_id],
    )
    services.workflow.set_resume_entries(session.session_id, [entry])
    assert client.post(f"{base}/resume-entries/{entry.entry_id}/approve").status_code == 200
    assert client.post(f"{base}/jobs/retrieve").status_code == 200
    edited = client.put(f"{base}/resume-entries/{entry.entry_id}", json={
        "heading": "Course API",
        "organisation_or_context": "Course planning",
        "details": ["Python API"],
        "bullets": ["Built a Python API for course planning"],
    })
    assert edited.status_code == 200
    body = edited.json()
    result = body["resume_entries"][0]
    assert result["status"] == "needs_review"
    assert result["heading"] == {"text": "Course API", "fact_ids": [fact.fact_id]}
    assert result["organisation_or_context"] == {
        "text": "Course planning", "fact_ids": [fact.fact_id]
    }
    assert result["details"] == [{
        "label": "Technology", "value": {"text": "Python API", "fact_ids": [fact.fact_id]}
    }]
    assert result["bullets"] == [{
        "text": "Built a Python API for course planning", "fact_ids": [fact.fact_id]
    }]
    assert result["source_fact_ids"] == [fact.fact_id]
    assert body["retrieval_results"] == []
    assert client.post(f"{base}/jobs/retrieve").status_code == 409


@pytest.mark.parametrize("extra", [
    {"source_fact_ids": ["forged"]},
    {"heading": {"text": "Heading", "fact_ids": ["forged"]}},
    {"details": [{"label": "Altered", "value": "Text"}]},
    {"status": "approved"},
    {"kind": "experience"},
])
def test_api_rejects_client_assigned_evidence(extra: dict[str, object]) -> None:
    client = TestClient(create_app(make_services()))
    base = confirmed_session(client)
    proposed = client.post(f"{base}/resume-entries/propose")
    assert proposed.status_code == 200
    before = client.get(base).json()
    entry_id = before["resume_entries"][0]["entry_id"]
    response = client.put(f"{base}/resume-entries/{entry_id}", json={
        "heading": "Updated heading", **extra,
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert client.get(base).json() == before


def test_api_rejects_changed_entry_item_counts() -> None:
    client = TestClient(create_app(make_services()))
    base = confirmed_session(client)
    proposed = client.post(f"{base}/resume-entries/propose")
    assert proposed.status_code == 200
    before = client.get(base).json()
    entry_id = before["resume_entries"][0]["entry_id"]
    response = client.put(f"{base}/resume-entries/{entry_id}", json={
        "heading": "Updated heading", "bullets": ["New uncited bullet"],
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert client.get(base).json() == before


@pytest.mark.parametrize("action", ["edit", "approve", "delete"])
def test_api_hides_missing_and_foreign_resume_entries(action: str) -> None:
    client = TestClient(create_app(make_services()))
    base = confirmed_session(client)
    other = confirmed_session(client)
    proposed = client.post(f"{other}/resume-entries/propose")
    assert proposed.status_code == 200
    foreign_id = proposed.json()["resume_entries"][0]["entry_id"]
    before = client.get(other).json()
    for session_base, entry_id, expected, code in [
        (base, "not-real", 404, "resume_entry_not_found"),
        (base, foreign_id, 404, "resume_entry_not_found"),
        ("/api/sessions/not-real", foreign_id, 404, "session_not_found"),
    ]:
        url = f"{session_base}/resume-entries/{entry_id}"
        if action == "edit":
            response = client.put(url, json={"heading": "Updated heading"})
        elif action == "approve":
            response = client.post(f"{url}/approve")
        else:
            response = client.delete(url)
        assert response.status_code == expected
        assert response.json()["error"]["code"] == code
    assert client.get(other).json() == before


def test_api_proposal_requires_confirmation() -> None:
    client = TestClient(create_app(make_services()))
    session_id = client.post("/api/sessions").json()["session_id"]
    response = client.post(f"/api/sessions/{session_id}/resume-entries/propose")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


def test_api_resume_entry_evidence_errors_use_safe_envelope() -> None:
    services = make_services()
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    proposed = client.post(f"{base}/resume-entries/propose")
    assert proposed.status_code == 200
    session = services.workflow.get_session(base.rsplit("/", 1)[1])
    entry = session.resume_entries[0]
    entry.heading.fact_ids = ["foreign-fact"]
    entry.source_fact_ids = ["foreign-fact"]
    response = client.post(f"{base}/resume-entries/{entry.entry_id}/approve")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resume_entry_evidence_error"
    assert session.resume_entries[0].status.value == "proposed"


@pytest.mark.parametrize("action", ["propose", "approve"])
def test_api_resume_entry_provider_failure_is_503(action: str) -> None:
    services = make_services()
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    path = "propose"
    if action == "approve":
        proposed = client.post(f"{base}/resume-entries/propose")
        assert proposed.status_code == 200
        path = f"{proposed.json()['resume_entries'][0]['entry_id']}/approve"
    before = client.get(base).json()
    services.resume_entries = ResumeEntryService(services.workflow, MissingOpenAIProvider())
    response = client.post(f"{base}/resume-entries/{path}")
    assert response.status_code == 503
    assert response.json() == {"error": {
        "code": "provider_unavailable",
        "message": "The AI provider is unavailable. Check the local configuration and try again.",
        "details": {},
    }}
    assert client.get(base).json() == before


def test_cors_allows_resume_entry_deletion() -> None:
    client = TestClient(create_app(make_services()))
    response = client.options("/api/sessions/session/resume-entries/entry", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "DELETE",
    })
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_api_approval_conflict_preserves_the_entry_edited_during_audit() -> None:
    services = make_services()
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    session_id = base.rsplit("/", 1)[1]
    entry = client.post(f"{base}/resume-entries/propose").json()["resume_entries"][0]

    class InterleavingProvider(EvidenceEchoCVProvider):
        def validate_resume_entries(self, entries, confirmed_facts):
            services.workflow.update_resume_entry(
                session_id, entry["entry_id"], ResumeEntryEdit(heading="Led 50 engineers")
            )
            return []

    services.resume_entries = ResumeEntryService(services.workflow, InterleavingProvider())
    response = client.post(f"{base}/resume-entries/{entry['entry_id']}/approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert "changed" in response.json()["error"]["message"]
    current = client.get(base).json()
    assert current["resume_entries"][0]["heading"]["text"] == "Led 50 engineers"
    assert current["resume_entries"][0]["status"] == "needs_review"


def test_api_stale_generation_cannot_restore_validation_or_export_after_entry_deletion() -> None:
    services = make_services()
    client = TestClient(create_app(services))
    base = confirmed_session(client)
    session_id = base.rsplit("/", 1)[1]
    approve_entries(client, base)
    jobs = client.post(f"{base}/jobs/retrieve").json()["retrieval_results"]
    assert client.post(f"{base}/jobs/{jobs[0]['document_id']}/select").status_code == 200
    stale_cv_ids = []
    after_deletion = {}

    class InterleavingProvider(EvidenceEchoCVProvider):
        def generate_cv(self, contact_facts, approved_entries, job):
            cv = super().generate_cv(contact_facts, approved_entries, job)
            stale_cv_ids.append(cv.cv_id)
            for entry in approved_entries:
                services.workflow.delete_resume_entry(session_id, entry.entry_id)
            after_deletion.update(services.workflow.get_session(session_id).model_dump(mode="json"))
            return cv

    services.cv = CVService(services.workflow, InterleavingProvider())
    response = client.post(f"{base}/cvs")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert "changed" in response.json()["error"]["message"]
    assert client.get(base).json() == after_deletion
    assert after_deletion["resume_entries"] == []
    assert after_deletion["selected_job_id"] is None
    assert after_deletion["cv"] is None
    for action in ["validate", "export"]:
        assert client.post(f"{base}/cvs/{stale_cv_ids[0]}/{action}").status_code == 409
    assert client.get(base).json() == after_deletion
