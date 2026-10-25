# Phase 2A: Real Voice UI integration — 24 October 2026

This is the Phase 2A checkpoint. The subsequent
[Phase 2B integration](real-feedback-ui-integration.md) now connects the Feedback
API and extends the browser handoff test through explicit feedback generation.

This checkpoint builds on merge commit `4b006c4` on
`feature/interview-ui-integration`. Changes are uncommitted for review.
The application now binds Luke's merged controller; Sunny's Feedback API remains
unbound for the next phase.

## Ownership and binding

- `frontend/src/features/interview/live/voiceBridge.ts` constructs
  `new RealtimeVoiceController(interviewApi(sessionId))`.
- UI notifications alias Luke's `VoiceEvent`. The UI controller port is a `Pick`
  of his public methods, shared with injected test and preview controllers.
  No generated records or event unions are copied.
- `useLiveInterview.ts` subscribes once per controller lifetime and delegates
  start/reconnect, mute, skip, playback recovery, finish and disconnect. Creating
  or mounting a controller does not request a microphone or start an interview.
- Luke's controller/session engine alone owns microphone tracks, WebRTC, token
  exchange, transcript persistence and progression. No files under
  `frontend/src/voice/`, backend code, generated contracts or dependencies change.
- The existing visualizer consumes controller activity through the UI reducer.
  The optional visualizer component boundary is retained for later orb/avatar work.
  No workbench styles or synthetic session endpoints are imported into the app.

Both API clients use `VITE_API_ROOT`, defaulting to `http://localhost:8000/api`.
The normal application backend owns the shared interview and realtime routes.
Luke's synthetic port-8010 workbench remains separate.

## UI corrections established by integration tests

Testing the real controller reproduced four failures across three UI behaviours:

1. Token and SDP failure can occur after `/start` has succeeded. Previously the
   UI retained a ready snapshot and stopped polling, leaving its timer at 10:00.
   Failed commands now refresh the canonical record without repeating a POST.
   The UI displays the running server deadline and offers explicit reconnect.
2. `finish()` can wait for pending ASR before the server changes phase. The screen
   now shows finishing and disables answer controls immediately while that command
   is pending. This does not mark the interview completed.
3. A failed end request leaves the controller in its internal finalizing state.
   The UI now calls its public `disconnect()` on finish rejection, releasing
   hardware and making reconnect available. It then reads the server state in case
   the end request actually committed before its response failed.

The fixes are confined to UI command handling and presentation. Luke's methods
and state machine are unchanged.

## Polling, finalization and cleanup

The two existing two-second polls are retained deliberately:

- The controller reads phase changes to mute new input and drain registered
  transcripts during finalization, then releases resources on terminal state.
- The UI reads full snapshots for `started_at`, question statuses, revisions and
  saved captions. Luke's events do not expose every full active/finalizing
  snapshot. UI reads are serial; stale or foreign snapshots are rejected.

This produces two GETs per steady connected polling interval, plus event/command
refreshes. Neither UI polling nor the countdown sends lifecycle POSTs. Tests
verify that the two loops coexist, keep the channel open during finalization,
ignore a stale UI GET arriving after controller completion, and stop polling a
completed interview. Consolidating the loops would require an agreed full-snapshot
notification from the controller; it is not necessary for this integration.

The UI uses only the terminal server snapshot for the Feedback handoff, retaining
its interview/context IDs, transcript revision and saved turns. Unconfirmed live
captions are not carried into the completed report context.

Leaving the room, navigating to CV Builder, page hide and unmount disconnect voice.
Unmount also removes subscriptions, page listeners and UI timers. Returning never
connects automatically, and leaving does not stop the server deadline. Tests also
cover Strict Mode effect cleanup and a microphone grant arriving after departure:
the late track is stopped without starting the interview.

A native microphone permission prompt can remain pending after disconnect; the
browser user must resolve it. Luke rejects overlapping connection attempts while
that promise is pending. The UI does not replace this guard or try to cancel a
browser permission prompt itself.

## Preview and feedback separation

`interview-preview.html` still injects `PreviewVoiceController`, displays
“UI preview · simulated interview” / “Microphone off · simulated”, and makes no
microphone, backend or provider requests. There is no automatic simulated fallback
when the real connection fails.

Completed real interviews open their own Feedback summary. `InterviewFeedback`
still supplies `source={null}` and offers a separately labelled fictional report.
No real feedback request or score is generated in this phase.

## Validation

The new component integration suite runs the default application bridge, both real
HTTP clients, Luke's controller/session engine and the React screen. Only hardware
and HTTP responses are mocked. Its 15 cases cover controls/events, permission,
token/SDP failures, blocked playback, reconnect, concurrent polling, transcript
draining, finish failure, stale reads and resource cleanup.

The new browser case runs CV → Setup → real controller → CV navigation/reconnect
→ finish → Feedback summary → saved transcript. It checks microphone/peer/playback
cleanup, one start/skip/end POST, two explicit connections and no Feedback POST.
The existing browser entry test now expects Start to be available while continuing
to prohibit automatic microphone access.

Final checks on 24 October 2026:

- **140 unit/component tests pass** across 12 files, including the 15 new real
  controller integration cases. Command: `npm --prefix frontend test -- --run --maxWorkers=1`.
- **31 Chrome E2E tests pass** in the full run, including existing CV export,
  Setup, Live preview, Feedback and Luke's workbench regressions.
  Command: `npm --prefix frontend run e2e`.
- ESLint, TypeScript and production build pass via `npm --prefix frontend run`
  `lint`, `typecheck` and `build`. `git diff --check` passes.
- Backend and generated contracts are unchanged. The backend suite was not rerun
  for this UI-only checkpoint; the known checksum baseline remains unchanged.

Browser tests ran outside the Windows sandbox to avoid the temporary-server
cleanup stall observed during the preceding merge checks. All hardware and provider
responses in the voice browser tests were mocked; no live trial was performed.

No human microphone or live-provider trial is claimed by these tests. A manual
trial should use the regular backend on port 8000 with a locally configured key,
then explicitly start a consented interview. Review microphone denial, blocked
playback, interruptions, connection loss, finish and the preserved transcript.
Real Feedback integration follows this review. The existing backend checksum
baseline remains documented in
[ui-integration.md](ui-integration.md#existing-windows-test-baseline).
