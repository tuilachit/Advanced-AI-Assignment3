# Provider error diagnosis — 25 October 2026

## Observed and unconfirmed

The running backend returned 200 for an initial profile conversation message and
503 for its follow-up. No profile facts were committed in the affected session.
The previous error handler mapped every provider exception to the same suggestion
to check local configuration, without logging the exception category. The exact
upstream cause of that historical failure therefore remains unconfirmed.

## Live checks

Four diagnostic Responses API calls used the existing backend-only local key and
configured `gpt-5.6-luna` model. Only synthetic candidate data was used. All four
completed successfully; no credentials or personal profile were written here.

- A 16-fact synthetic input produced a completed tool response (1,065 output tokens).
- The rich Jamie Tran demo with a clarified target role produced a completed tool
  response (957 output tokens).
- A full isolated agent exchange using Jamie's demo profile with one target role
  completed both extraction and acknowledgement (1,029 and 63 output tokens).
  It saved 12 draft facts, with no missing required categories.

These checks establish current access and a successful extraction path, not a
reproduction or proven repair of the historical failure. The model, output budget,
confirmation gates, and realtime model were not changed.

## Diagnostic repair

The API now distinguishes invalid model responses, connection failures,
authentication rejection, exhausted quota, rate limiting, access denial, and
upstream outages. It logs only the classified category, exception class names,
and upstream HTTP status, never raw errors, credentials, or candidate payloads.
Error instructions allow for previously saved changes rather than promising that
a failed multi-step message rolled back all work.

Seven API regression cases failed before the change and passed afterward. They
exercise safe messages, diagnostic logs, sensitive-detail exclusion and unchanged
session data when failure precedes any tool execution. The full backend suite
completed successfully (603 cases). Ruff and mypy (using the backend project
configuration, 33 source files) passed. The backend was restarted with the existing
local key; backend health and frontend requests returned HTTP 200. Temporary
sessions were cleared by this restart.

No commit, push, or deployment was performed for this diagnostic repair.

## Follow-up: reproduced truncation and root-cause repair

The next user attempt produced a `ProviderProtocolError` caused by `JSONDecodeError`
before any profile facts were saved. Replaying the previously drafted 7,785-character
Luke profile in an isolated diagnostic request reproduced the failure:

- response status: `incomplete`;
- reason: `max_output_tokens`;
- output tokens: exactly the configured 1,200;
- function arguments: 5,363 characters, with an unterminated string at position 5,212.

The smaller synthetic success above was not sufficient coverage of this richer input.
The root problem was an undersized output allowance plus parsing before checking
completion. Strict tool schemas do not make truncated JSON complete. The
[official structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs#json-mode)
documents checking incomplete responses before parsing JSON.

Repair:

- Profile interaction now allows 6,000 output tokens, with one retry at 12,000 only
  when the API explicitly reports `max_output_tokens` truncation.
- Partial response content is never appended to the conversation or executed as a tool.
- Resume-entry proposal, entry validation, CV generation and CV validation use the
  same bounded output allowances. They inspect the raw response envelope before
  invoking the SDK's strict structured parser, which otherwise raises before the
  caller can inspect completion status.
- Failed/content-filtered output is rejected without retry. Completed malformed
  JSON is not silently repaired. Existing citations, validation and explicit approval
  gates remain in force. No model switch or credential change was made.

Live extraction checks with the full Luke prompt:

- First fixed run: 1,335 output tokens for extraction and 93 for acknowledgement;
  21 draft facts, with the ambiguous target role still requiring clarification.
- Second fixed run: 1,408 output tokens for extraction and 155 for acknowledgement;
  23 draft facts, zero missing required categories. All facts remained draft.

Personal profile text and raw model output are not included in this repository.
These runs validate extraction, not independent truth of candidate claims.

Fifteen regression cases cover rich-profile capacity, retry-before-mutation,
bounded retry exhaustion, non-completed responses with syntactically valid JSON,
and all four structured operations. Structured cases use the installed OpenAI SDK
with an offline HTTP transport rather than mocking away its JSON parser. The new
failure/recovery cases were observed failing before the repair. The existing
completed-malformed-JSON rejection test already passed and was retained.

Full backend suite after repair: **618 passed**. Ruff passed; mypy passed using
the backend project configuration (33 source files).

A live structured-output check using ten synthetic confirmed facts completed in
2,134 output tokens and produced eight proposed resume entries. The normal
resume-entry service accepted their evidence references; none were auto-approved.

After restarting the local backend with the repair, an HTTP smoke test submitted
the full Luke prompt and clarified the target role where necessary. It returned
HTTP 200 with 22 draft facts, `profile_review`, and a target-role fact. No profile
confirmation or resume-entry approval was performed for that real-profile test.
The varying 21/23/22 fact counts reflect model grouping across runs, not a fixed
assertion that every detail has identical coverage; explicit user review remains
required. The original truncation failure did not recur in these fixed runs.
