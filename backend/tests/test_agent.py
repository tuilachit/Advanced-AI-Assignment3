import json
from copy import deepcopy
from typing import Any

import pytest

from app.domain.models import SessionState
from app.domain.workflow import SessionWorkflow
from app.providers.base import ProviderTurn, ToolCall
from app.providers.fake import ScriptedProvider
from app.services.agent import AGENT_TOOLS, AgentService, AgentStepLimitError


def agent_service(
    workflow: SessionWorkflow,
    provider: ScriptedProvider,
) -> AgentService:
    def empty_callback(_session_id: str) -> dict[str, object]:
        return {}

    return AgentService(
        workflow,
        provider,
        retrieve_jobs=empty_callback,
        generate_cv=empty_callback,
    )


def test_agent_applies_draft_profile_facts_but_cannot_confirm_them() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    provider = ScriptedProvider(
        [
            ProviderTurn(
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        name="update_profile",
                        arguments={
                            "facts": [
                                {"field": "name", "value": "Maya Chen"},
                                {"field": "skills", "value": "Python and SQL"},
                            ]
                        },
                    )
                ]
            ),
            ProviderTurn(message="I captured those as draft facts. Please review them."),
        ]
    )

    result = agent_service(workflow, provider).handle_message(
        session.session_id,
        "I am Maya and I use Python and SQL.",
    )

    stored = workflow.get_session(session.session_id)
    assert result.message == "I captured those as draft facts. Please review them."
    assert stored.state is SessionState.PROFILE_REVIEW
    assert {fact.field for fact in stored.profile.facts} == {"name", "skills"}
    assert all(fact.status.value == "draft" for fact in stored.profile.facts)
    assert result.observations[0].success is True
    assert {tool["name"] for tool in provider.seen_tools[0]} == {
        "update_profile",
        "retrieve_jobs",
        "generate_cv",
    }
    assert "confirm_profile" not in {tool["name"] for tool in AGENT_TOOLS}


def test_agent_reports_repeated_tool_calls_without_reapplying_them() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    repeated = ToolCall(
        call_id="call-1",
        name="update_profile",
        arguments={"facts": [{"field": "name", "value": "Maya Chen"}]},
    )
    provider = ScriptedProvider(
        [
            ProviderTurn(tool_calls=[repeated]),
            ProviderTurn(tool_calls=[repeated.model_copy(update={"call_id": "call-2"})]),
            ProviderTurn(message="The duplicate update was ignored."),
        ]
    )

    result = agent_service(workflow, provider).handle_message(session.session_id, "I am Maya.")

    assert len(workflow.get_session(session.session_id).profile.facts) == 1
    assert result.observations[1].success is False
    assert result.observations[1].error == "Repeated tool call ignored."


def test_agent_stops_after_six_tool_steps() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
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
    provider = ScriptedProvider(turns)

    with pytest.raises(AgentStepLimitError, match="six"):
        agent_service(workflow, provider).handle_message(session.session_id, "Keep going.")

    assert len(workflow.get_session(session.session_id).profile.facts) == 6


def test_agent_rejects_invalid_tool_arguments_as_an_observation() -> None:
    workflow = SessionWorkflow()
    session = workflow.create_session()
    provider = ScriptedProvider(
        [
            ProviderTurn(
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        name="update_profile",
                        arguments={"facts": [{"field": "name", "value": "  "}]},
                    )
                ]
            ),
            ProviderTurn(message="Please provide a non-empty name."),
        ]
    )

    result = agent_service(workflow, provider).handle_message(
        session.session_id, "My name is blank."
    )

    assert result.observations[0].success is False
    assert "blank" in (result.observations[0].error or "")
    assert workflow.get_session(session.session_id).profile.facts == []


def test_follow_up_retains_prior_question_and_user_context_only_in_its_session() -> None:
    class CapturingProvider(ScriptedProvider):
        inputs: list[list[dict[str, Any]]] = []

        def respond(
            self, *, input_items: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> ProviderTurn:
            self.inputs.append(deepcopy(input_items))
            return super().respond(input_items=input_items, tools=tools)

    workflow = SessionWorkflow()
    first = workflow.create_session()
    second = workflow.create_session()
    provider = CapturingProvider(
        [
            ProviderTurn(message="Which project used Python: the planner or the chatbot?"),
            ProviderTurn(message="The chatbot used Python."),
            ProviderTurn(message="Tell me about your project."),
        ]
    )
    service = agent_service(workflow, provider)
    service.handle_message(first.session_id, "I built a planner and a chatbot.")
    service.handle_message(first.session_id, "The second one.")
    service.handle_message(second.session_id, "I have a project.")

    follow_up = json.dumps(provider.inputs[1])
    assert "I built a planner and a chatbot." in follow_up
    assert "Which project used Python: the planner or the chatbot?" in follow_up
    assert "The second one." in follow_up
    assert "chatbot" not in json.dumps(provider.inputs[2])
    assert "input_items" not in first.model_dump_json()
