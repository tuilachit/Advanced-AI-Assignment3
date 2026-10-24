# Real Voice Integration preparation — 23 October 2026

This is the pre-merge preparation checkpoint. For the subsequent controller
binding and current validation, see
[Phase 2A: Real Voice UI integration](real-voice-ui-integration.md).

## Scope and dependency

This checkpoint builds on UI commit `51eb2bf` on
`feature/interview-ui-integration`. It prepares UI event handling and connection
lifecycle behaviour without connecting real audio. Following UI review, these
changes are prepared as a separate local commit, preserving `51eb2bf`. No push,
PR creation, merge or cherry-pick is part of this checkpoint.

[Luke's PR #2](https://github.com/tuilachit/Advanced-AI-Assignment3/pull/2) was
open, non-draft and unmerged when reviewed at
`022a352e954a5ef8ca82bd062c4904865fdfa86e`. GitHub metadata was checked, then the
matching local remote reference was inspected with read-only `git show` calls.
Reviewed `frontend/src/voice/controller.ts`, `types.ts`, `interviewApi.ts` and
`docs/a3/voice-integration.md`. No files were copied from or changed on that branch.

The current branch lacks Luke's controller/session engine, token endpoint and
generated credential schema. The main app therefore retains
`voiceIntegration.createController: () => null`, its unavailable-voice explanation
and a disabled Start button. There is no dynamic import, alternative transport,
fake endpoint or simulated fallback in the application binding.

## Safe UI changes completed

| File | Change and purpose |
| --- | --- |
| `frontend/src/features/interview/live/useLiveInterview.ts` | Invalidate pending UI commands on disconnect, hidden navigation, page hide, completion and controller replacement. Check command identity before applying connect failures or finish results, reset attachment on a new controller, and refresh status on page restore without automatically connecting. |
| `live/useLiveInterview.ts` | Apply controller events to the current state synchronously before React renders. A delayed status-request failure cannot add an obsolete connection warning after a completion event in the same batch. Existing subscriptions, timers and page listeners are removed on unmount. |
| `live/liveState.ts` | Reject snapshots for another session/interview/context or older flow/transcript revisions. Preserve final captions and canonical turn order during active updates. Terminal snapshots provide the saved transcript, rather than retaining unconfirmed live captions in the feedback context. Ignore late transcript/activity/question updates after completion and question changes during finalization. |
| `live/liveState.ts` | Clear a controller `api_unreachable` warning after an accepted successful status read. Preserve unrelated microphone/playback errors until their own recovery action. |
| `live/LiveInterviewStage.tsx` | During an actual-controller connection attempt, show “Microphone access requested · connecting.” Luke obtains the microphone before WebRTC is connected, so “Microphone off” would be misleading during that interval. The simulated preview continues to say “Microphone off · simulated.” |
| `live/voiceBridge.ts` | Clarify the temporary UI port and future owner-type imports; the real factory remains unbound. |
| `live/LiveInterviewStage.test.tsx`, new `live/liveState.test.ts`, `frontend/e2e/live-interview.spec.ts` | Add lifecycle, stale-event/snapshot, canonical completion and simulated-cancellation regressions. |

The UI still delegates all start, mute, playback recovery, skip, finish and
disconnect actions to the injected controller. It does not implement microphone
capture, credentials, WebRTC, answer persistence, question generation or backend
progression. Setup, Feedback presentation, CV logic, generated contracts,
dependency files and backend code are unchanged.

Read-only status polling remains every two seconds while an interview is active,
finalizing or connecting/connected, including when the mounted stage is hidden.
Leaving the stage releases voice; it does not pause the backend deadline. An old
finish command can still complete on the server after UI cancellation; later
canonical GET responses remain authoritative. “Cancel” here means invalidating
the pending UI callback, not cancelling the interview or backend work.

## Event contract already consumed by the UI

The existing small port structurally matches Luke's documented API at the inspected
head. The shared records are aliases to the merged generated schema. This review
does not claim a compiled import-level check against his unmerged modules.

| Notification | UI behaviour |
| --- | --- |
| `connection` with disconnected/connecting/connected/failed | Connection label, microphone wording and available controls. No automatic connect/reconnect on mount or page restoration. |
| `activity` with candidate/interviewer activity and mute state | Listening/speaking/user-speaking/muted visualizer states and microphone button state. No inferred volume, emotion or confidence. |
| `question` with `flow_revision` | Display the server-issued question, including follow-ups linked to their main question. Reject stale flow events; do not generate/select the next question. |
| `transcript` with a generated `TranscriptTurn` | Reconcile by stable turn ID/version, retain final captions against partial updates, render plain text and distinguish provisional/failed/interrupted turns. |
| `finished` with a generated `Interview` | Use the accepted canonical record. `finalizing` still waits; `completed` enables Feedback. Cancelled/failed interviews remain distinct terminal outcomes. Late captions cannot alter the completed feedback snapshot. |
| `error` with code/message/retryability | Render the controller's safe error and supported recovery controls. A status read only clears an API-connectivity warning, not blocked playback or microphone denial. |

`connect(interviewId)` selects the interview before requesting microphone access,
starts it if ready, and repeats its current question on reconnect.
`disconnect()` only releases local voice resources. `finish()` owns transcript
draining and ending; a freshly constructed controller needs an interview selected
by `connect()` before it can finish. The UI's existing attach-before-end guard is
retained and now resets when the controller instance changes.

Luke's `disconnect()` invalidates an outstanding connection attempt, but the
browser's microphone permission promise may remain pending until the user resolves
the prompt. His controller rejects overlapping `connect()` calls while that attempt
is pending. UI callbacks from the old attempt are now ignored after cancellation;
there is no UI-side replacement for permission cancellation or his connection lock.
Verify that UX with the real controller once available.

## Exact remaining work after PR #2 is integrated

1. Make the complete reviewed voice dependency available through the team's normal
   process. Its controller depends on `InterviewVoiceSession`, `interviewApi`,
   generated voice types, the backend token provider/router and app wiring. Do not
   copy just the controller or cherry-pick core files into this UI feature.
2. In `live/voiceBridge.ts`, import Luke's modules and replace the null factory:

   ```ts
   import { RealtimeVoiceController } from '../../../voice/controller'
   import { interviewApi } from '../../../voice/interviewApi'

   // In the existing stable voiceIntegration object:
   createController: (sessionId) =>
     new RealtimeVoiceController(interviewApi(sessionId))
   ```

   The snippet documents the future binding; these imports are not added to the
   current application. Alias `VoiceNotification` to Luke's exported `VoiceEvent`
   and derive `VoiceController` from his public method subset when those types
   exist locally. Keep injected test controllers compatible with that subset.
3. Use one backend/session for CV setup, UI status reads and the voice client.
   Both clients currently use `VITE_API_ROOT` with the same port-8000 default.
   Luke's synthetic port-8010 workbench has separate sessions and is not the
   product integration. His controller calls the active-interview-only
   `POST /api/sessions/{session_id}/interviews/{interview_id}/realtime-token`;
   UI components must not request credentials or repeat lifecycle POSTs.
4. Keep the canonical status read for `started_at`, phase and revisions. Luke's
   current events do not provide a full started/finalizing snapshot. Both layers
   poll every two seconds; agree a single full-snapshot source with Luke before
   removing either poll. During finalization, retain his channel for pending
   transcript draining, and wait for backend completion before feedback.
5. Keep the current visualizer for initial functional integration. If adopting
   Luke's `VoiceOrbView`, wrap its isolated DOM refs in a React component and bind
   `VoiceIntegration.Visualizer`; unsubscribe on cleanup and scope styles. Account
   for initial/finalizing state and preserve accessible status text. Do not import
   his entire workbench UI or add advanced animations in this phase.
6. Run import/type checks and integration tests using the actual controller with
   its injectable fake platform/API. Then do a separately labelled live human
   microphone trial with the backend key configured locally. Test permission
   denial, unresolved/cancelled permission prompts, blocked playback, mute,
   interrupted speech, skip, follow-up, connection loss/reconnect, page/navigation
   cleanup, time limit and final transcript draining. Current fake-controller
   tests cannot establish WebRTC compatibility or microphone/provider quality.
7. Before real Feedback integration, agree with Luke, Sunny and Tien on submitted
   answer IDs, control utterances, timing across connection clocks and the final
   transcript revision. Keep Sunny's endpoint/type dependency separate; no
   feedback API or evaluation logic is added in this checkpoint.

## Verification and limits

New regression cases were run against the existing implementation first and
reproduced the stale-state/lifecycle issues. Final results on 23 October 2026:

- **85 unit/component tests pass** across seven files: the previous 67 plus 18
  new lifecycle/state regressions (eight component cases and ten reducer cases).
- **26 Chrome E2E tests pass**: all 25 previous checks plus cancellation/restart
  in the explicitly simulated preview. Existing CV, Setup and Feedback checks
  remain green, including CV export and responsive layouts.
- ESLint, TypeScript and the production build pass. The build still emits only
  the normal application HTML entry, not the standalone preview pages.
- `git diff --check` passes. Backend, generated schemas, dependencies and CV
  functionality have no changes. The backend suite was not rerun for this UI-only
  checkpoint; the existing baseline below remains unchanged.

Commands: `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`,
`npm --prefix frontend test -- --run`, `npm --prefix frontend run build` and
`npm --prefix frontend run e2e`.

These checks were repeated before the local commit. The first unit run, concurrent
with build/browser checks, timed out in the existing CV whitespace-save test
(`App.test.tsx`); 84 other tests passed. With the browser suite finished, the
unchanged unit suite passed all 85 tests in 6.61 seconds. All 26 browser tests,
lint, typecheck and build passed. No test timeout or application code was changed
to obtain the passing rerun.

The tests inject a small controller double or use the explicitly scripted preview;
they make no microphone, token or provider calls. All preview labels remain
visible, and mock feedback still belongs to its separate fictional interview.
This is preparation evidence, not evidence that real voice is connected.
Page-hide/restore behaviour is covered using browser events in component tests;
actual browser back-forward-cache behaviour with real microphone access remains
part of the later live trial.

The existing Windows backend checksum failure remains documented in
[ui-integration.md](ui-integration.md#existing-windows-test-baseline). No unrelated
backend test fix or dependency installation is part of this work.
