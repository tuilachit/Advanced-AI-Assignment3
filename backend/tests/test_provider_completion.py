"""Regression for rich-profile tool JSON truncated at the old 1200-token cap."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI

from app.domain.models import CVDocument, Job
from app.domain.workflow import SessionWorkflow
from app.providers.base import ProviderProtocolError
from app.providers.openai_provider import OpenAIModelProvider
from app.services.agent import AGENT_TOOLS, AgentService


def response(status="completed", reason=None, arguments=None, text=""):
    output = []
    if arguments is not None:
        output.append(
            SimpleNamespace(
                type="function_call",
                call_id="profile-call",
                name="update_profile",
                arguments=arguments,
            )
        )
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        output=output,
        output_text=text,
    )


class Responses:
    def __init__(self, results):
        self.results = iter(results)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.results)


def test_truncated_profile_is_retried_before_any_facts_are_saved():
    workflow = SessionWorkflow()
    session = workflow.create_session()
    payload = json.dumps(
        {
            "facts": [
                {"field": "experience_internship", "value": "Built Python reporting endpoints."},
                {"field": "project_retrieval", "value": "Evaluated a coursework retrieval system."},
            ]
        }
    )

    class InspectingResponses(Responses):
        def create(self, **kwargs):
            if len(self.requests) == 1:
                assert session.profile.facts == []
            return super().create(**kwargs)

    responses = InspectingResponses(
        [
            response("incomplete", "max_output_tokens", '{"facts": [{"field": "name"'),
            response(arguments=payload),
            response(text="Review and confirm your facts."),
        ]
    )
    provider = OpenAIModelProvider(model="offline", client=SimpleNamespace(responses=responses))
    agent = AgentService(workflow, provider, retrieve_jobs=lambda _: {}, generate_cv=lambda _: {})
    result = agent.handle_message(session.session_id, "My internship and retrieval project.")
    assert result.message == "Review and confirm your facts."
    assert [f.field for f in session.profile.facts] == [
        "experience_internship",
        "project_retrieval",
    ]
    assert len(result.observations) == 1
    assert all(f.status.value == "draft" for f in session.profile.facts)
    first, retry, _ = responses.requests
    assert retry["max_output_tokens"] > first["max_output_tokens"]
    assert retry["max_output_tokens"] <= 12000
    assert retry["input"] == first["input"]
    assert retry["store"] is False
    assert retry["parallel_tool_calls"] is False


def test_rich_profile_has_room_for_more_than_1200_output_tokens():
    class BudgetResponses:
        def create(self, **kwargs):
            if kwargs["max_output_tokens"] < 4000:
                return response("incomplete", "max_output_tokens", '{"facts": [')
            return response(arguments='{"facts": [{"field": "project", "value": "Built an API"}]}')

    provider = OpenAIModelProvider(
        model="offline", client=SimpleNamespace(responses=BudgetResponses())
    )
    turn = provider.respond(
        input_items=[{"role": "user", "content": "A rich profile"}], tools=AGENT_TOOLS
    )
    assert turn.tool_calls[0].arguments["facts"][0]["value"] == "Built an API"


@pytest.mark.parametrize(
    "status,reason",
    [
        ("incomplete", "content_filter"),
        ("failed", None),
        ("in_progress", None),
    ],
)
def test_non_completed_output_never_executes_even_valid_json(status, reason):
    responses = Responses([response(status, reason, '{"facts": []}')])
    provider = OpenAIModelProvider(model="offline", client=SimpleNamespace(responses=responses))
    with pytest.raises(ProviderProtocolError):
        provider.respond(input_items=[], tools=AGENT_TOOLS)
    assert len(responses.requests) == 1


def test_exhausted_completion_retry_stops_without_partial_profile_changes():
    responses = Responses(
        [
            response("incomplete", "max_output_tokens", '{"facts": []}'),
            response("incomplete", "max_output_tokens", '{"facts": []}'),
        ]
    )
    provider = OpenAIModelProvider(model="offline", client=SimpleNamespace(responses=responses))
    with pytest.raises(ProviderProtocolError):
        provider.respond(input_items=[], tools=AGENT_TOOLS)
    assert len(responses.requests) == 2


def test_completed_malformed_json_is_not_silently_repaired_or_retried():
    responses = Responses([response(arguments='{"facts": [')])
    provider = OpenAIModelProvider(model="offline", client=SimpleNamespace(responses=responses))
    with pytest.raises(ProviderProtocolError):
        provider.respond(input_items=[], tools=AGENT_TOOLS)
    assert len(responses.requests) == 1


@pytest.mark.parametrize("operation", ["entries", "entry_validation", "cv", "cv_validation"])
def test_structured_operations_check_completion_before_sdk_json_parsing(operation):
    requests = []
    cv = CVDocument(target_job_id="demo-job", headline="Computing student")
    completed = {
        "entries": {"entries": []},
        "entry_validation": {"issues": []},
        "cv": cv.model_dump(mode="json"),
        "cv_validation": {"issues": []},
    }[operation]

    def handler(request):
        requests.append(json.loads(request.content))
        first = len(requests) == 1
        return httpx.Response(
            200,
            json={
                "id": "resp-offline",
                "object": "response",
                "created_at": 0,
                "model": "offline",
                "status": "incomplete" if first else "completed",
                "incomplete_details": {"reason": "max_output_tokens"} if first else None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg-offline",
                        "role": "assistant",
                        "status": "incomplete" if first else "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": '{"unfinished":' if first else json.dumps(completed),
                            }
                        ],
                    }
                ],
            },
        )

    with OpenAI(
        api_key="offline-not-a-real-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        provider = OpenAIModelProvider(model="offline", client=client)
        if operation == "entries":
            result = provider.propose_resume_entries([])
        elif operation == "entry_validation":
            result = provider.validate_resume_entries([], [])
        elif operation == "cv":
            result = provider.generate_cv(
                [], [], Job(document_id="demo-job", title="Role", description="Work")
            )
        else:
            result = provider.validate_claims(cv, [])
    assert result == (cv if operation == "cv" else [])
    assert len(requests) == 2
    assert requests[1]["max_output_tokens"] > requests[0]["max_output_tokens"]
    assert requests[1]["input"] == requests[0]["input"]
    assert requests[1]["text"]["format"]["strict"] is True
    assert requests[1]["store"] is False


@pytest.mark.parametrize(
    "status,reason,text,attempts",
    [
        ("incomplete", "max_output_tokens", '{"entries": []}', 2),
        ("incomplete", "content_filter", '{"entries": []}', 1),
        ("failed", None, '{"entries": []}', 1),
        ("completed", None, '{"entries":', 1),
    ],
)
def test_structured_failures_are_bounded_and_never_accepted(status, reason, text, attempts):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "resp-offline",
                "object": "response",
                "created_at": 0,
                "model": "offline",
                "status": status,
                "incomplete_details": {"reason": reason} if reason else None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg-offline",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "annotations": [], "text": text}],
                    }
                ],
            },
        )

    with OpenAI(
        api_key="offline-not-a-real-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        provider = OpenAIModelProvider(model="offline", client=client)
        with pytest.raises(ProviderProtocolError):
            provider.propose_resume_entries([])
    assert len(requests) == attempts


@pytest.mark.parametrize(
    "operation", ["agent", "entries", "entry_validation", "cv", "cv_validation"]
)
def test_model_requests_override_short_shared_client_timeout(operation):
    requests = []
    cv = CVDocument(target_job_id="demo-job", headline="Computing student")
    payload = {
        "agent": {},
        "entries": {"entries": []},
        "entry_validation": {"issues": []},
        "cv": cv.model_dump(mode="json"),
        "cv_validation": {"issues": []},
    }[operation]

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "resp-timeout-test",
                "object": "response",
                "created_at": 0,
                "model": "offline",
                "status": "completed",
                "incomplete_details": None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg-timeout",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "annotations": [], "text": json.dumps(payload)}
                        ],
                    }
                ],
            },
        )

    with OpenAI(
        api_key="offline-not-a-real-key",
        timeout=30,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        provider = OpenAIModelProvider(model="offline", client=client)
        if operation == "agent":
            provider.respond(input_items=[], tools=AGENT_TOOLS)
        elif operation == "entries":
            provider.propose_resume_entries([])
        elif operation == "entry_validation":
            provider.validate_resume_entries([], [])
        elif operation == "cv":
            provider.generate_cv(
                [], [], Job(document_id="demo-job", title="Role", description="Work")
            )
        else:
            provider.validate_claims(cv, [])
        assert client.timeout == 30  # Voice/other users of this client are unchanged.
    assert requests[0].extensions["timeout"]["read"] == 120
