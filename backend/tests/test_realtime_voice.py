from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from test_interview_flow import build, make_interview, ready_session, start

from app.main import create_app
from app.providers.base import ProviderUnavailableError


def active_interview(provider: Any = None) -> tuple[TestClient, Any, str, dict[str, Any]]:
    initial, services = build()
    base = ready_session(initial)
    interview = make_interview(initial, base)
    started = start(initial, base, interview)["interview"]
    client = (
        TestClient(create_app(services, realtime_provider=provider))
        if provider is not None
        else initial
    )
    return client, services, f"{base}/interviews/{interview['interview_id']}", started


def test_no_configured_voice_provider_returns_recoverable_error() -> None:
    client, _services, url, _interview = active_interview()
    response = client.post(f"{url}/realtime-token")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert response.headers["cache-control"] == "no-store"


class TokenProvider:
    model = "gpt-realtime-2"

    def __init__(self) -> None:
        self.contexts: list[Any] = []
        self.failure = False

    def issue(self, context: Any) -> dict[str, Any]:
        self.contexts.append(context)
        if self.failure:
            raise ProviderUnavailableError("sensitive-upstream-error")
        return {"client_secret": "ephemeral-fixture", "expires_at": 4_000_000_000}


def test_voice_token_is_bound_to_active_interview_and_never_stored() -> None:
    provider = TokenProvider()
    client, services, url, interview = active_interview(provider)
    response = client.post(f"{url}/realtime-token")
    assert response.status_code == 200
    body = response.json()
    assert body["client_secret"] == "ephemeral-fixture"
    assert body["model"] == "gpt-realtime-2"
    assert body["connection_id"].startswith("connection-")
    assert response.headers["cache-control"] == "no-store"
    assert provider.contexts[0].job.document_id == "graduate_ai_engineer"
    assert "ephemeral-fixture" not in client.get(url).text
    assert (
        "ephemeral-fixture"
        not in services.interviews.get_context(
            interview["session_id"], interview["interview_id"]
        ).model_dump_json()
    )


def test_failed_mint_does_not_invalidate_existing_connection_or_leak_error() -> None:
    provider = TokenProvider()
    client, services, url, interview = active_interview(provider)
    connection = services.interviews.bind_connection(
        interview["session_id"], interview["interview_id"]
    )
    provider.failure = True
    response = client.post(f"{url}/realtime-token")
    assert response.status_code == 503
    assert "sensitive-upstream-error" not in response.text
    # An existing connection must still be allowed to submit/control the interview.
    response = client.post(
        f"{url}/end",
        json={
            "request_id": "end-after-failed-mint",
            "expected_flow_revision": 1,
            "connection_id": connection,
        },
    )
    assert response.status_code == 200


def test_foreign_and_terminal_interviews_do_not_mint_credentials() -> None:
    provider = TokenProvider()
    client, _services, url, _interview = active_interview(provider)
    foreign = client.post("/api/sessions").json()["session_id"]
    foreign_url = f"/api/sessions/{foreign}/interviews/{url.split('/')[-1]}"
    assert client.post(f"{foreign_url}/realtime-token").status_code == 404
    client.post(f"{url}/end", json={"request_id": "end", "expected_flow_revision": 1})
    assert client.post(f"{url}/realtime-token").status_code == 409
    assert provider.contexts == []


def test_ready_interview_does_not_mint_before_consent_checked_by_start() -> None:
    provider = TokenProvider()
    initial, services = build()
    base = ready_session(initial)
    interview = make_interview(
        initial,
        base,
        consent={
            "send_audio_to_provider": False,
            "retain_transcript_for_feedback": False,
        },
    )
    client = TestClient(create_app(services, realtime_provider=provider))
    url = f"{base}/interviews/{interview['interview_id']}/realtime-token"
    assert client.post(url).status_code == 409
    assert provider.contexts == []


def test_provider_payload_uses_native_audio_transcription_and_bounded_tools() -> None:
    from app.providers.realtime import OpenAIRealtimeProvider

    class Secrets:
        def create(self, **payload: Any) -> Any:
            self.payload = payload
            return type(
                "Credential", (), {"value": "ephemeral-fixture", "expires_at": 4_000_000_000}
            )()

    secrets = Secrets()
    sdk = type("SDK", (), {"realtime": type("Realtime", (), {"client_secrets": secrets})()})()
    provider = OpenAIRealtimeProvider(api_key=None, client=sdk)
    _client, services, _url, interview = active_interview()
    context = services.interviews.get_context(interview["session_id"], interview["interview_id"])
    result = provider.issue(context)
    assert result["client_secret"] == "ephemeral-fixture"
    session = secrets.payload["session"]
    assert session["model"] == "gpt-realtime-2"
    transcription = session["audio"]["input"]["transcription"]
    assert transcription["model"] == "gpt-4o-transcribe"
    assert transcription["language"] == "en"
    assert "Python" in transcription["prompt"]
    assert "SQL" in transcription["prompt"]
    assert context.job.description not in transcription["prompt"]
    assert session["audio"]["input"]["noise_reduction"] == {"type": "far_field"}
    assert session["audio"]["output"] == {"voice": "marin", "speed": 1.0}
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["tool_choice"] == "required"
    assert {tool["name"] for tool in session["tools"]} == {
        "advance_interview",
        "repeat_question",
        "continue_listening",
    }
    assert "Graduate AI Engineer" in session["instructions"]
    assert "API_KEY" not in session["instructions"]


def test_voice_settings_validate_device_and_speed_overrides(monkeypatch: Any) -> None:
    import pytest
    from pydantic import ValidationError

    from app.settings import Settings

    monkeypatch.setenv("OPENAI_VOICE", "cedar")
    monkeypatch.setenv("OPENAI_VOICE_SPEED", "0.95")
    monkeypatch.setenv("OPENAI_INPUT_NOISE_REDUCTION", "near_field")
    settings = Settings.from_environment()
    assert settings.openai_voice == "cedar"
    assert settings.openai_voice_speed == 0.95
    assert settings.openai_input_noise_reduction == "near_field"
    monkeypatch.setenv("OPENAI_VOICE_SPEED", "2")
    with pytest.raises(ValidationError):
        Settings.from_environment()
