from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import Field, ValidationError

from app.domain.models import AgentObservation, FactInput, StrictModel, TraceEvent
from app.domain.profile_fields import PROFILE_FIELD_GUIDANCE
from app.domain.workflow import SessionWorkflow
from app.providers.base import AgentModelProvider, ProviderProtocolError, ToolCall


class AgentStepLimitError(RuntimeError):
    pass


class AgentRun(StrictModel):
    message: str
    observations: list[AgentObservation] = Field(default_factory=list)


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "update_profile",
        "description": "Save only profile facts explicitly stated by the user as draft facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "description": PROFILE_FIELD_GUIDANCE},
                            "value": {"type": "string"},
                        },
                        "required": ["field", "value"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["facts"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "retrieve_jobs",
        "description": "Retrieve relevant jobs after the user has confirmed the profile.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "generate_cv",
        "description": "Generate a CV after the user selects a retrieved job.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class AgentService:
    def __init__(
        self,
        workflow: SessionWorkflow,
        provider: AgentModelProvider,
        *,
        retrieve_jobs: Callable[[str], dict[str, object]],
        generate_cv: Callable[[str], dict[str, object]],
        max_tool_steps: int = 6,
    ) -> None:
        self._workflow = workflow
        self._provider = provider
        self._retrieve_jobs = retrieve_jobs
        self._generate_cv = generate_cv
        self._max_tool_steps = max_tool_steps
        self._conversations: dict[str, list[dict[str, Any]]] = {}

    def handle_message(self, session_id: str, message: str) -> AgentRun:
        session = self._workflow.get_session(session_id)
        conversation = self._conversations.setdefault(session_id, [])
        input_items: list[dict[str, Any]] = [
            *conversation,
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "session": session.model_dump(mode="json", exclude={"trace"}),
                        "missing_fields": self._workflow.missing_required_fields(session),
                    }
                ),
            },
        ]
        # Retain only user-visible turns, never provider reasoning or tool internals.
        # Keep the user's turn even if a later provider step fails after a tool commits.
        conversation.append({"role": "user", "content": message})
        observations: list[AgentObservation] = []
        fingerprints: set[str] = set()
        tool_steps = 0

        while tool_steps < self._max_tool_steps:
            turn = self._provider.respond(input_items=input_items, tools=AGENT_TOOLS)
            if turn.tool_calls:
                input_items.extend(turn.output_items or self._tool_items(turn.tool_calls))
                for call in turn.tool_calls:
                    if tool_steps >= self._max_tool_steps:
                        raise AgentStepLimitError(
                            "The agent reached its six tool-step safety limit."
                        )
                    tool_steps += 1
                    fingerprint = json.dumps(
                        {"name": call.name, "arguments": call.arguments}, sort_keys=True
                    )
                    if fingerprint in fingerprints:
                        observation = AgentObservation(
                            action=call.name,
                            success=False,
                            error="Repeated tool call ignored.",
                        )
                    else:
                        fingerprints.add(fingerprint)
                        observation = self._execute_tool(session_id, call)
                    observations.append(observation)
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": observation.model_dump_json(),
                        }
                    )
                continue

            if not turn.message.strip():
                raise ProviderProtocolError("The model returned neither a message nor a tool call.")
            current = self._workflow.get_session(session_id)
            conversation.append({"role": "assistant", "content": turn.message})
            current.trace.append(
                TraceEvent(
                    event_type="agent_response",
                    summary=turn.message,
                    details={"tool_steps": tool_steps},
                )
            )
            return AgentRun(message=turn.message, observations=observations)

        raise AgentStepLimitError("The agent reached its six tool-step safety limit.")

    def _execute_tool(self, session_id: str, call: ToolCall) -> AgentObservation:
        try:
            if call.name == "update_profile":
                raw_facts = call.arguments.get("facts")
                if not isinstance(raw_facts, list):
                    raise ValueError("update_profile requires a facts list.")
                facts = [FactInput.model_validate(item) for item in raw_facts]
                session = self._workflow.update_profile(
                    session_id,
                    facts,
                    source_reference=f"message-{uuid4()}",
                )
                result: dict[str, object] = {
                    "updated_fields": [fact.field for fact in facts],
                    "state": session.state.value,
                    "missing_fields": self._workflow.missing_required_fields(session),
                }
            elif call.name == "retrieve_jobs":
                result = self._retrieve_jobs(session_id)
            elif call.name == "generate_cv":
                result = self._generate_cv(session_id)
            else:
                raise ValueError(f"Unknown tool: {call.name}")
            return AgentObservation(action=call.name, success=True, result=result)
        except (ValueError, ValidationError) as error:
            return AgentObservation(action=call.name, success=False, error=str(error))

    @staticmethod
    def _tool_items(calls: list[ToolCall]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function_call",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": json.dumps(call.arguments),
            }
            for call in calls
        ]
