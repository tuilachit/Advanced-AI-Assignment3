from __future__ import annotations

from types import SimpleNamespace
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


def test_production_startup_voice_route_uses_the_live_interview_store(monkeypatch: Any) -> None:
    from app import main
    from app.settings import Settings

    provider = TokenProvider()
    _initial, runtime_services = build()
    offline_build = main.build_default_services
    calls = 0

    def build_at_startup(settings: Any = None, *, client: Any = None) -> Any:
        nonlocal calls
        calls += 1
        return offline_build(Settings()) if calls == 1 else runtime_services

    monkeypatch.setattr(main, "build_default_services", build_at_startup)
    monkeypatch.setattr(main.Settings, "from_environment", lambda: Settings())
    with TestClient(create_app(realtime_provider=provider)) as client:
        base = ready_session(client)
        interview = make_interview(client, base)
        start(client, base, interview)
        url = f"{base}/interviews/{interview['interview_id']}"
        response = client.post(f"{url}/realtime-token")
        assert response.status_code == 200
        assert response.json()["model"] == "gpt-realtime-2"
        assert len(provider.contexts) == 1
        assert client.get(f"{url}/feedback").json()["feedback_status"] == "not_requested"


def test_default_voice_provider_uses_startup_settings_and_shared_client(monkeypatch: Any) -> None:
    from app import main
    from app.providers import realtime
    from app.settings import Settings

    _initial, runtime_services = build()
    original_build = main.build_default_services
    payloads: list[dict[str, Any]] = []
    closed: list[bool] = []

    def issue(**payload: Any) -> Any:
        payloads.append(payload)
        return SimpleNamespace(value="ephemeral-fixture", expires_at=4_000_000_000)

    sdk = SimpleNamespace(
        realtime=SimpleNamespace(client_secrets=SimpleNamespace(create=issue)),
        close=lambda: closed.append(True),
    )

    def unexpected_client(**kwargs: Any) -> Any:
        raise AssertionError("Realtime must reuse the application-owned SDK client")

    monkeypatch.setattr(main, "OpenAI", lambda **kwargs: sdk)
    monkeypatch.setattr(realtime, "OpenAI", unexpected_client)
    monkeypatch.setattr(
        main,
        "build_default_services",
        lambda settings=None, client=None: (
            runtime_services if client is sdk else original_build(Settings())
        ),
    )
    monkeypatch.setattr(
        main.Settings,
        "from_environment",
        lambda: Settings(
            openai_api_key="fixture-not-a-key",
            openai_voice="cedar",
            openai_voice_speed=0.95,
            openai_input_noise_reduction="near_field",
        ),
    )
    app = create_app()
    assert payloads == [] and closed == []
    with TestClient(app) as client:
        base = ready_session(client)
        interview = make_interview(client, base)
        start(client, base, interview)
        response = client.post(f"{base}/interviews/{interview['interview_id']}/realtime-token")
        assert response.status_code == 200
        assert response.json()["model"] == "gpt-realtime-2"
        assert payloads[0]["session"]["audio"]["output"] == {"voice": "cedar", "speed": 0.95}
        assert payloads[0]["session"]["audio"]["input"]["noise_reduction"] == {"type": "near_field"}
        assert closed == []
    assert closed == [True]


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
