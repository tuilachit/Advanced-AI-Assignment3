# UI integration readiness — 23 October 2026

This records the review before commit `51eb2bf`. Subsequent UI lifecycle changes
and the current voice handoff are documented in
[voice-ui-preparation.md](voice-ui-preparation.md).

## Review outcome and scope

The current work stays within Mio's UI & Integration responsibilities. The
frontend checks below pass, including the existing CV Builder regressions. The
screens are ready for a Draft PR describing the UI and its integration boundaries;
real voice and real evaluation are not connected yet.

Reviewed branch: `feature/interview-ui-integration`, based on `bd17ff4` (merged
Interview Flow PR #1). At this checkpoint **all UI changes are still uncommitted**;
the feature branch HEAD has no commits beyond the local `main` baseline. The
review includes tracked modifications and all untracked feature, preview, test
and documentation files, rather than only a committed branch diff.

| Files | Scope and review finding |
| --- | --- |
| `frontend/src/App.tsx`, `components/StageNav.tsx` | Add the Interview destination and mount its workspace; existing workflow callbacks and stage gating are retained. |
| `frontend/src/components/CVStage.tsx` | Adds an optional navigation callback and CTA only when the current saved CV is export-ready. Save, validation and PDF export logic are unchanged. |
| `frontend/src/api.ts`, `types.ts` | Add interview creation/read calls and aliases to the already generated Interview Flow schema. No handwritten wire models. |
| `frontend/src/styles.css` | Increases mobile navigation text from 10px to 12px. Feature styles use dedicated selectors and existing design tokens. |
| `frontend/src/features/interview/` | Setup form, request handling, live presentation/controller boundary, feedback presentation/source boundary, explicit samples and development previews. No provider, WebRTC, grading or backend progression implementation. |
| `frontend/src/test/interviewFixtures.ts`, new interview E2E/component tests | Synthetic fixtures and regression coverage. The scripted controller is a development preview, not a fallback voice service in the app. |
| `frontend/e2e/workflow.spec.ts` | Only the expected navigation-tab count changes from five to six; existing regression assertions are preserved. |
| `frontend/interview-preview.html`, `feedback-preview.html` | Separate development entry points; the normal production build emits neither page. The explicit sample-feedback option remains available in the app and is always labelled. |
| `docs/a3/ui-integration.md`, this document, `ui-draft-pr.md` | Contribution evidence, integration handoff and proposed PR body. |

No changes to `backend/`, `data/`, `frontend/openapi.json`,
`frontend/src/generated/`, dependency manifests/lockfile or teammate-owned voice
modules. No branches were changed, merged or overwritten, and nothing was
committed, pushed or published during this review. No blocking issue was found
for the UI-only scope. The unfinished adapters and cases below prevent calling
this a complete live end-to-end integration.

## Current teammate PR status

Checked through GitHub on 23 October 2026. The local read-only remote references
match these exact live PR head SHAs, so their files were inspected with `git show`
without checking out or merging either branch.

| PR | Verified state | Available implementation | Outstanding dependency |
| --- | --- | --- | --- |
| [#2 — Luke: realtime interview voice and orb workbench](https://github.com/tuilachit/Advanced-AI-Assignment3/pull/2) | Open, not draft, not merged; head `022a352e954a5ef8ca82bd062c4904865fdfa86e` | `RealtimeVoiceController`, `InterviewVoiceSession`, voice API client, token route/provider, generated credential schema, imperative `VoiceOrbView`, separate workbench and tests | Team review and integration of the complete dependency, then Mio's React binding and combined-flow verification |
| [#3 — Sunny: interview feedback evaluation system](https://github.com/tuilachit/Advanced-AI-Assignment3/pull/3) | Open draft, not merged; head `179d2c94ff345f9d2e519c6fffca1396f13e7bfb` | Validated models, structured provider, evidence validation, metrics, report generation and background-job orchestration | HTTP routes, application/provider/job-runner wiring, public response contract and generated frontend schema |

GitHub reports both mergeable at this snapshot, but that is not review approval.
Neither PR has a review submission or discussion comment. The connector returned
no commit status entries or pull-request-triggered Actions runs for either head;
their PR descriptions contain author-reported local tests, not verified green
GitHub CI. Those teammate suites were not rerun on this UI branch.

The UI file inventory has **no changed-file overlap** with either PR's current
file list. Future backend/router/settings and generated-schema changes belong in
the owners' integration process. Luke's PR also includes two Interview Flow
request-ID fixes; these are part of his reviewed dependency, not Mio's UI changes.
Recheck overlap and contract generation when either head changes.

## Voice binding: exact next changes

Prerequisite: Luke's full PR becomes available through the team's agreed
integration process. Importing just his controller file is insufficient: it
depends on his session engine, API client, token endpoint and generated types.
Do not copy these into the UI feature or implement competing endpoint calls.

1. In `frontend/src/features/interview/live/voiceBridge.ts`, import
   `RealtimeVoiceController` from `../../../voice/controller` and `interviewApi`
   from `../../../voice/interviewApi`. Replace the null factory with
   `(sessionId) => new RealtimeVoiceController(interviewApi(sessionId))`.
   Keep the integration object stable across renders. Alias the notification type
   to Luke's `VoiceEvent` and derive the UI controller port from his public methods
   (for example `Pick<RealtimeVoiceController, ...>`) once those imports exist.
   This retains injectable test controllers without maintaining parallel contracts.
2. Keep `useLiveInterview.ts` as the subscription, command-delegation and cleanup
   owner. Its existing interface matches the inspected controller: `subscribe`,
   `connect`, `set_muted`, `resume_audio`, `skip`, `finish`, `disconnect`.
   Start/reconnect must remain explicit user actions. The controller handles
   microphone permission, starting a ready interview, token exchange, WebRTC,
   transcript persistence and progression. The UI must not also POST those actions.
3. Continue reading the canonical interview for phase, timestamps and revisions.
   Luke emits connection/activity/transcript/question/finished/error events but
   does not emit a full snapshot at start or during finalization. The current
   UI poll and Luke's connected poll both run every two seconds. Keep the UI read
   initially; agree with Luke on one snapshot source before removing either poll.
   Do not derive the server start time from the browser's connect event.
4. Keep `finalizing` separate from `completed`: mute/disable new answers, retain
   the channel while the controller drains pending transcription, and offer
   feedback only after the backend reports `completed`. Disconnecting or leaving
   releases local audio without ending or pausing the server interview.
   A fresh controller currently needs `connect(id)` before `finish()` has an ID;
   the existing reconnect-before-end guard must remain unless Luke adds another
   supported attachment method.
5. Reuse the existing visualizer slot without delaying functional voice wiring.
   If Luke's orb is adopted, add a React wrapper such as `LukeVoiceVisualizer.tsx`
   and register it as `VoiceIntegration.Visualizer`. `VoiceOrbView` takes three
   DOM elements and exposes `ready()`/`handle(event)`; it is not a React component.
   Give it isolated refs, unsubscribe on cleanup and scope the needed styling.
   Do not import the entire workbench stylesheet into Evidence CV. The wrapper
   must account for initial/reconnected and finalizing state, which the orb's
   event-only state machine does not fully represent. Keep current accessible
   status text and reduced-motion support. Advanced animations remain deferred.
6. Extend `LiveInterviewStage.test.tsx` and `e2e/live-interview.spec.ts` to exercise
   the actual controller with an injected fake platform/API, then perform a
   separately labelled human microphone smoke test when the dependency is ready.

Both existing API clients use `VITE_API_ROOT`, defaulting to
`http://localhost:8000/api`. Setup, GET polling, voice and feedback must use the
same backend instance and session ID. Luke's port-8010 synthetic workbench is a
separate application; its sessions must not be mixed with the normal port-8000
CV workflow. His production token route is
`POST /api/sessions/{session_id}/interviews/{interview_id}/realtime-token` and
accepts only active interviews. The controller owns its ephemeral credentials.
The permanent provider key remains in the backend's ignored environment file.

## Feedback binding: contract and exact next changes

Sunny's current `FeedbackResult`/`FeedbackFailure` are service dataclasses, not
an exposed HTTP response contract. Do not guess URLs, status codes or manually
add them to generated TypeScript. Sunny needs to supply routes, register the
service/router against the same Interview Flow instance, wire the provider and
job runner, and export their supported public schemas. Regenerate OpenAPI and
TypeScript with the existing generator after those changes are integrated.

Current service semantics to preserve:

- Feedback starts only for `completed` interviews with matching
  `expected_transcript_revision`. `FeedbackRequest` carries that revision and a
  `request_id`; it does not require the browser to resend transcript contents.
- `start()` admits/reuses work and returns `feedback_status: generating`, even
  when an existing evaluation can be reused. Always read the result afterwards.
- `get_result()` is read-only and returns `not_requested`, `generating`, `ready`
  or `failed`, with a report or safe error as appropriate. It never starts/retries
  work. A POST that observes failed work explicitly retries it. Stable request
  IDs bind to stable inputs; changed revision/context cannot reuse that identity.
- Only submitted final candidate turns for answered questions support grading.
  Planned questions are excluded; skipped/unusable asked questions remain
  unscored with insufficient evidence. Evidence quotes must be exact text from
  a turn belonging to that answer. No overall score is defined.
- WPM uses valid provider/recording timing and separates audio clocks. Fillers
  count preserved transcript tokens. Pause analysis is currently unavailable.
  The UI must preserve methods, coverage and unavailable reasons.

Proposed UI work once the HTTP contract exists:

| File | Change |
| --- | --- |
| New `frontend/src/features/interview/feedback/feedbackApi.ts` | Small client using generated request/response aliases, the common API root and abort signals; expose the confirmed start/read operations. No job execution or scoring in the browser. |
| New `frontend/src/features/interview/feedback/serviceFeedbackSource.ts` | Read existing status, start only when needed, poll until terminal, map the report, and stop local requests/timers on abort. Keep request identity stable for one interview/context/revision and avoid duplicate work. |
| `feedback/feedbackView.ts` | Keep presentation models separate from DTOs. Extend the source boundary to distinguish opening/reloading a report from an explicit failed-job retry, and carry safe error code/retryability/recovery action. |
| `feedback/useFeedback.ts`, `FeedbackStage.tsx` | Preserve server error semantics instead of the present catch-all message. Retry recoverable transport/job failures; reload the canonical interview for revision conflicts; show expired-session or terminal errors without an endless retry loop. Refreshing a snapshot requires a callback to update the parent interview. Abort polling on leaving the view, including hidden navigation if the stage stays mounted. |
| `feedback/InterviewFeedback.tsx` | Bind a stable service source for the actual completed interview. Keep mock data only behind the explicitly labelled sample selection/preview; never fall back to sample grades after a real API error. |
| `frontend/src/types.ts` | Add aliases to generated feedback schemas only after they exist. Preserve `schema_version`/`rubric_version` compatibility; retain `report_id` for result identity/diagnostics without inventing a UI score. |
| Feedback component/E2E tests and new adapter tests | Exercise status transitions, explicit retry vs read-only reload, abort, duplicate clicks, stale revisions, no-answer reports, evidence mapping and missing/zero metric values using the real exported contract. |

Suggested adapter flow: read status on **View feedback**; use an existing ready
report; continue polling a generating job; start a not-requested job once. A
failed job should show its error and wait for an explicit retry action before a
new POST. A polling/network retry should first read status rather than blindly
starting another attempt. Exact HTTP paths, envelopes, status codes, polling
interval/backoff and any `Retry-After` support still need agreement with Sunny.
Aborting browser polling must not imply that a backend evaluation was cancelled.

Map `question_feedback` by `question_id`; `technical_reasoning` to
`technicalReasoning`; `improvement` to `suggestion`; `generated_at` to `createdAt`;
and `turn_id`/`quote` to evidence links. Preserve assessed scores 0–4 separately
from not-applicable/insufficient-evidence states. Validate interview ID, context
hash and transcript revision before rendering. Keep the existing exact-quote
display guard; Sunny's backend remains responsible for submitted-turn provenance
and assessment validity. Map metric status/value/unit/method/reason/turn IDs
without replacing null values with zero or creating an aggregate score.

## Coordination checklist and implementation order

| Owner(s) | Agreement or evidence needed |
| --- | --- |
| Luke + Mio | Reviewed controller dependency; stable public method/event imports; common API root; snapshot polling responsibility; finalization and reconnect behaviour; optional orb wrapper boundary |
| Sunny + Mio | Published start/read HTTP contract and generated types; typed error/retry/revision-conflict behaviour; provider/job-runner application wiring; polling cadence and report-version policy |
| Luke + Sunny + Tien | Exercise real submitted turn IDs and provider VAD timing across follow-ups, skips, reconnects, finish/time-limit drains and failed ASR. Feedback must use the completed canonical transcript revision. |
| Luke + Sunny | Confirm treatment of spoken control utterances such as “repeat the question.” The inspected voice engine gathers unconsumed candidate turns for the current question, while feedback trusts submitted IDs. A control utterance could accompany a later submitted answer. This is a code-review integration risk, not a reproduced live failure; agree and test the policy in owner code rather than filtering or rewriting transcripts in the UI. |
| Team | Normal review/integration of PR #2 and completed PR #3; coordinate shared router/settings/generated-schema edits, and regenerate rather than hand-resolve generated types |

Sequence for the MVP: review this UI Draft PR proposal; make Luke's dependency
available through the team process; wire/test real voice with the current
visualizer; review voice behaviour; make Sunny's route contract available;
wire/test feedback; then verify CV → Setup → voice answers/follow-up → finish →
real report → CV export. Visual polish and advanced animations follow that flow.
No teammate messages or approval requests were sent as part of this review.

Acceptance checks for the combined flow must include permission denial, blocked
playback, mute, skip, interruption, disconnect/reconnect, navigation cleanup,
pending-transcript completion, time-limit completion, provider/API failures,
feedback job retry and stale-report rejection. Include desktop/mobile browser
layout and a real human microphone trial; fixtures alone cannot establish voice
quality or live feedback validity.

## Fresh verification evidence

Run on this UI working tree on 23 October 2026:

| Check | Result |
| --- | --- |
| `npm --prefix frontend run lint` | Pass |
| `npm --prefix frontend run typecheck` | Pass |
| `npm --prefix frontend test -- --run` | 67 passed across six files: 29 existing, 9 Setup, 14 Live, 15 Feedback |
| `npm --prefix frontend run build` | Pass; normal index-only production build; separate preview HTML pages absent |
| `npm --prefix frontend run e2e` | 25 Chrome tests passed: 10 existing CV, 4 Setup, 5 Live, 6 Feedback |
| API contract check, Windows equivalent | Pass: export backend OpenAPI and run installed `openapi-typescript --alphabetize` into ignored `tmp/dev/pr-review-contract/`, then compare both files with CRLF normalized to LF; tracked generated files untouched |
| `git diff --check` | Pass |

The POSIX `contract:check` script expects `.venv/bin/python`; this Windows run
used `.venv/Scripts/python.exe -X utf8 backend/export_openapi.py` and the installed
`frontend/node_modules/.bin/openapi-typescript.cmd` instead. This is the same
export/generation comparison with explicit line-ending normalization, not a
claim that the unmodified shell script ran on Windows.

CV regression evidence covers resume-entry approval gates, rejected export,
validated PDF download, export relocking after edits, sequential job/CV changes,
profile invalidation, provider-error recovery and independent sessions. Interview
browser checks also cover returning to CV export, responsive 1440/768/375px
layouts, keyboard evidence navigation, reduced motion and labelled mock states.
These tests use fixtures/scripted previews; no live provider or microphone calls
were made during this review. They support preservation of existing tested CV
behaviour, not an assertion that every possible live scenario has been tested.

The earlier offline browser-to-FastAPI setup smoke check and 51 passing Interview
Flow backend tests are recorded in [the implementation notes](ui-integration.md).
They were not rerun for this documentation review. The unchanged full backend
baseline remains **268 passed, 1 failed**:
`backend/tests/test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid`.
It is the existing Windows CRLF/raw-byte dataset checksum issue. No unrelated
backend/data/Git configuration fix is included.

## Draft PR preparation

Proposed title and complete body: [ui-draft-pr.md](ui-draft-pr.md). Before eventual
publication, stage/commit only the reviewed frontend and `docs/a3/` files, inspect
the staged diff and recheck teammate heads. Local environment files, `tmp/`, build
outputs and screenshots under `artifacts/generated/` or `frontend/test-results/`
remain ignored. Screenshots are local review artifacts, not GitHub attachments.

Do not push or create the Draft PR until the user has reviewed the proposal.
Publication and real integration remain future actions.
