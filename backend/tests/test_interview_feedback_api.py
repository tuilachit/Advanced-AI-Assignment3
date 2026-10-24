import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_interview_feedback import (
    orchestration,
    report,
)
from test_interview_feedback import (
    preparation_fixture as preparation_fixture,
)

from app.domain.feedback_models import FeedbackResponse
from app.main import create_app
from app.providers.base import ProviderUnavailableError


def api(fixture, provider=None, runner=None):
    service, runner, provider, prepared = orchestration(fixture, provider=provider, runner=runner)
    # The API uses exactly the flow that owns the prepared interview.
    services = fixture[2].app.state.services
    client = TestClient(create_app(services, feedback_service=service))
    url = (
        f"/api/sessions/{prepared.interview.session_id}/interviews/"
        f"{prepared.interview.interview_id}/feedback"
    )
    return client, url, prepared.request.model_dump(), runner, provider


def test_all_success_states_reuse_and_get_never_schedules(preparation_fixture):
    client, url, request, runner, provider = api(preparation_fixture)
    assert client.get(url).json() == {
        "feedback_status": "not_requested",
        "report": None,
        "error": None,
    }
    assert runner.jobs == provider.calls == []
    response = client.post(url, json=request)
    assert response.status_code == 202
    assert response.json() == {"feedback_status": "generating"}
    for _ in range(3):
        assert client.get(url).json()["feedback_status"] == "generating"
    assert client.post(url, json=request).status_code == 202
    assert len(runner.jobs) == 1 and provider.calls == []
    runner.run_next()
    ready = client.get(url).json()
    assert ready["feedback_status"] == "ready"
    assert ready["report"]["report_id"] == "job-report" and ready["error"] is None
    assert client.post(url, json=request | {"request_id": "reuse"}).status_code == 202
    assert client.get(url).json() == ready
    assert runner.jobs == [] and len(provider.calls) == 1


@pytest.mark.parametrize("failure", [ProviderUnavailableError, RuntimeError])
def test_safe_failure_and_explicit_retry(preparation_fixture, failure):
    class Failing:
        def assess(self, value):
            raise failure("SECRET credential prompt transcript")

    client, url, request, runner, _ = api(preparation_fixture, provider=Failing())
    assert client.post(url, json=request).status_code == 202
    runner.run_next()
    for _ in range(3):
        response = client.get(url)
        assert response.status_code == 200
        body = response.json()
        assert body["feedback_status"] == "failed" and body["report"] is None
        assert body["error"]["error"]["details"] == {"retryable": True}
        assert "SECRET" not in response.text
    assert runner.jobs == []
    assert client.post(url, json=request).status_code == 202
    assert len(runner.jobs) == 1


def test_errors_and_validation(preparation_fixture, monkeypatch):
    client, url, request, runner, _ = api(preparation_fixture)
    assert client.get(url.replace("/interviews/", "/interviews/missing-")).status_code == 404
    assert (
        client.post(url.replace("/interviews/", "/interviews/missing-"), json=request).status_code
        == 404
    )
    for invalid in [
        {},
        request | {"extra": True},
        request | {"request_id": " "},
        request | {"expected_transcript_revision": True},
    ]:
        assert client.post(url, json=invalid).status_code == 422
    assert client.post(url, json=request | {"expected_transcript_revision": 999}).status_code == 409
    assert runner.jobs == []
    flow = preparation_fixture[1]
    monkeypatch.setattr(
        flow, "set_feedback_status", lambda *args: (_ for _ in ()).throw(RuntimeError("SECRET"))
    )
    response = client.post(url, json=request)
    assert response.status_code == 503 and "SECRET" not in response.text
    assert runner.jobs == []


def test_request_id_conflict(preparation_fixture):
    client, url, request, runner, _ = api(preparation_fixture)
    assert client.post(url, json=request).status_code == 202
    assert client.post(url, json=request | {"expected_transcript_revision": 999}).status_code == 409
    assert len(runner.jobs) == 1


@pytest.mark.parametrize("state", ["not_requested", "generating", "ready", "failed"])
def test_strict_response_states(state):
    payload = {"feedback_status": state}
    if state == "ready":
        payload["report"] = report()
    if state == "failed":
        payload["error"] = {"error": {"code": "safe", "message": "Please retry."}}
    assert FeedbackResponse.model_validate(payload).feedback_status == state
    for field in ("report", "error"):
        invalid = payload | {
            field: None
            if field in payload
            else (report() if field == "report" else {"error": {"code": "safe", "message": "safe"}})
        }
        with pytest.raises(ValidationError):
            FeedbackResponse.model_validate(invalid)
    with pytest.raises(ValidationError):
        FeedbackResponse.model_validate(payload | {"extra": True})


def test_incomplete_interview_and_foreign_session(preparation_fixture):
    from test_interview_feedback import ManualFeedbackRunner

    from app.providers.interview_feedback import UnavailableInterviewFeedbackProvider
    from app.services.interview_feedback import InterviewFeedbackService

    _, flow, original_client, base, interview, _, _, session_id = preparation_fixture
    runner = ManualFeedbackRunner()
    service = InterviewFeedbackService(flow, UnavailableInterviewFeedbackProvider(), runner=runner)
    app = create_app(original_client.app.state.services, feedback_service=service)
    client = TestClient(app)
    url = f"{base}/interviews/{interview['interview_id']}/feedback"
    request = {
        "request_id": "feedback",
        "expected_transcript_revision": flow.get(
            session_id, interview["interview_id"]
        ).transcript_revision,
    }
    assert client.post(url, json=request).status_code == 409
    foreign = client.post("/api/sessions").json()["session_id"]
    foreign_url = url.replace(session_id, foreign)
    assert client.get(foreign_url).status_code == 404
    assert client.post(foreign_url, json=request).status_code == 404
    assert runner.jobs == []
