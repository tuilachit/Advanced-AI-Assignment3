from threading import Event, Thread
from threading import enumerate as threads
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_api import make_services

from app import main
from app.services.feedback_runtime import FeedbackRuntime
from app.settings import Settings


def test_runtime_is_lazy_two_workers_and_drains_without_retry(monkeypatch):
    before = {thread.ident for thread in threads()}
    runtime = FeedbackRuntime()
    assert {thread.ident for thread in threads()} == before
    started = [Event(), Event()]
    release = Event()
    completed = []

    def job(index):
        started[index].set()
        assert release.wait(5)
        completed.append(index)

    runtime.submit(lambda: job(0))
    runtime.submit(lambda: job(1))
    assert all(event.wait(5) for event in started)
    runtime.submit(lambda: completed.append(2))
    closed = Event()
    draining = Event()
    shutdown = runtime._executor.shutdown

    def observed_shutdown(**kwargs):
        assert kwargs == {"wait": True, "cancel_futures": False}
        draining.set()
        shutdown(**kwargs)

    monkeypatch.setattr(runtime._executor, "shutdown", observed_shutdown)

    def close():
        runtime.shutdown()
        closed.set()

    closer = Thread(target=close)
    closer.start()
    assert draining.wait(5)
    assert not closed.is_set()
    try:
        with pytest.raises(RuntimeError):
            runtime.submit(lambda: completed.append(3))
    finally:
        release.set()
        closer.join(5)
    assert closed.is_set() and sorted(completed) == [0, 1, 2]
    runtime.shutdown()


def test_injected_services_and_openapi_never_read_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Credentials or SDK accessed")

    monkeypatch.setattr(main.Settings, "from_environment", forbidden)
    monkeypatch.setattr(main, "OpenAI", forbidden)
    monkeypatch.setattr(main, "FeedbackRuntime", forbidden)
    app = main.create_app()
    assert "/feedback" in str(app.openapi())
    services = make_services()
    injected = SimpleNamespace()
    app = main.create_app(services, feedback_service=injected)
    with TestClient(app):
        assert app.state.services is services
        assert app.state.feedback_service is injected


@pytest.mark.parametrize("fail_at", [None, "services", "runner", "feedback"])
def test_startup_resources_and_partial_failure_cleanup(monkeypatch, fail_at):
    events = []
    services = make_services()
    original_build = main.build_default_services

    def build(settings=None, *, client=None):
        if client is None:
            return original_build(Settings())
        events.append("services")
        if fail_at == "services":
            raise RuntimeError("startup")
        return services

    def client(**kwargs):
        assert kwargs == {"api_key": "fake-key", "timeout": 30.0, "max_retries": 0}
        events.append("client")
        return SimpleNamespace(close=lambda: events.append("close"))

    class Runner:
        def __init__(self):
            events.append("runner")
            if fail_at == "runner":
                raise RuntimeError("startup")

        def shutdown(self):
            events.append("drain")

    def feedback(flow, provider, *, runner):
        events.append("feedback")
        assert flow is services.interviews
        assert provider._model == "configured-model"
        if fail_at == "feedback":
            raise RuntimeError("startup")
        return SimpleNamespace(flow=flow)

    monkeypatch.setattr(main, "build_default_services", build)
    monkeypatch.setattr(
        main.Settings,
        "from_environment",
        lambda: Settings(openai_api_key="fake-key", openai_model="configured-model"),
    )
    monkeypatch.setattr(main, "OpenAI", client)
    monkeypatch.setattr(main, "FeedbackRuntime", Runner)
    monkeypatch.setattr(main, "InterviewFeedbackService", feedback)
    app = main.create_app()
    app.openapi()
    assert events == []
    if fail_at:
        with pytest.raises(RuntimeError, match="startup"), TestClient(app):
            pass
    else:
        with TestClient(app):
            assert app.state.feedback_service.flow is services.interviews
            assert events == ["client", "services", "runner", "feedback"]
    assert events[-1] == "close"
    if fail_at in {None, "feedback"}:
        assert events[-2:] == ["drain", "close"]
    else:
        assert "drain" not in events


def test_unavailable_provider_and_missing_configuration(monkeypatch):
    from app.providers.base import ProviderUnavailableError
    from app.providers.interview_feedback import UnavailableInterviewFeedbackProvider

    with pytest.raises(ProviderUnavailableError):
        UnavailableInterviewFeedbackProvider().assess(None)

    monkeypatch.setattr(main.Settings, "from_environment", lambda: Settings())
    monkeypatch.setattr(main, "OpenAI", lambda **kwargs: pytest.fail("SDK created"))
    app = main.create_app()
    with TestClient(app):
        feedback = app.state.feedback_service
        assert feedback._flow is app.state.services.interviews
        assert isinstance(feedback._provider, UnavailableInterviewFeedbackProvider)
        assert feedback._runner is not None
    with pytest.raises(RuntimeError):
        feedback._runner.submit(lambda: None)


def test_client_closed_even_if_drain_raises(monkeypatch):
    events = []
    monkeypatch.setattr(main.Settings, "from_environment", lambda: Settings(openai_api_key="fake"))
    monkeypatch.setattr(
        main, "OpenAI", lambda **kwargs: SimpleNamespace(close=lambda: events.append("close"))
    )
    original_build = main.build_default_services
    services = make_services()
    monkeypatch.setattr(
        main,
        "build_default_services",
        lambda settings=None, client=None: services if client else original_build(Settings()),
    )

    class Runner:
        def shutdown(self):
            events.append("drain")
            raise RuntimeError("drain failed")

    monkeypatch.setattr(main, "FeedbackRuntime", Runner)
    with pytest.raises(RuntimeError, match="drain failed"), TestClient(main.create_app()):
        pass
    assert events == ["drain", "close"]


def test_runner_does_not_retry_failed_work():
    runtime = FeedbackRuntime()
    calls = []

    def fail():
        calls.append("called")
        raise RuntimeError("fake failure")

    runtime.submit(fail)
    runtime.shutdown()
    assert calls == ["called"]
