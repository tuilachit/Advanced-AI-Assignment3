# Agent Actions and Observations

## Provider boundary

The agent exposes exactly three strict tools:

- `update_profile(facts)` saves user-supplied facts as drafts.
- `retrieve_jobs()` is permitted only after profile confirmation.
- `generate_cv()` is permitted only after job selection.

There is deliberately no `confirm_profile` tool. Confirmation is a user action. Calls are serial (`parallel_tool_calls=False`), responses are not stored by the provider (`store=False`), repeated calls are ignored, and a message stops after at most six tool steps.

## Deterministic Action-Observation trace

Source: `test_agent_applies_draft_profile_facts_but_cannot_confirm_them`.

```text
State before: collecting_profile
User input: I am Maya and I use Python and SQL.
Action: update_profile
Arguments: name=Maya Chen; skills=Python and SQL
Python function: SessionWorkflow.update_profile(...)
Observation: success=true; updated_fields=[name, skills]; state=profile_review
Final response: I captured those as draft facts. Please review them.
State after: profile_review
```

The test verifies that both facts remain `draft`, the profile cannot be confirmed by the model, and all three available tools use strict schemas.

## Safety-path observations

| Scenario | Observed result | Test |
| --- | --- | --- |
| Model repeats the same profile tool call | The second call returns `success=false` with `Repeated tool call ignored.`; only one fact is stored | `test_agent_reports_repeated_tool_calls_without_reapplying_them` |
| Blank fact value | Tool validation returns a failed Observation and the session remains unchanged | `test_agent_rejects_invalid_tool_arguments_as_an_observation` |
| More than six tool steps | The service raises a recoverable step-limit error after six updates | `test_agent_stops_after_six_tool_steps` |
| Provider missing or unavailable | API returns a safe 503 error and the React session remains usable | `workflow.spec.ts` provider-failure test |

## Live trace

The post-reranker live records retain allowlisted model messages, tool calls, observations, state
transitions and stop outcomes. Raw provider response objects and provider response IDs are
deliberately excluded. This preserves the evidence needed to inspect the workflow without storing
provider internals.

| Scenario | Observed action and outcome | Evidence |
| --- | --- | --- |
| Complete profile | One `update_profile` action captured eight user-supplied fields, moved the session to `profile_review`, and asked only for user confirmation. No unnecessary information-gathering question was recorded. | [complete-agent](../06_Live_Evaluation/records/post-reranker-2026-09-09/complete-agent/service-evidence.json) |
| Incomplete profile | The model first asked for a target direction, then recorded the supplied direction and asked for a name; after the name it asked for contact details. The bounded run retained two distinct useful follow-ups without inventing absent contact details. | [incomplete-agent](../06_Live_Evaluation/records/post-reranker-2026-09-09/incomplete-agent/service-evidence.json) |
