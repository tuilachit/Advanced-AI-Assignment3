# Local native voice integration — Luke

This branch builds on Tien's PR #1 at `663ad542b92c79d1a5b66eedffe4b219c5b68d70`.
It adds the native audio adapter and a development workbench. It does not implement Sunny's
feedback service or replace Mio's interview screens. Sunny's feedback API is now integrated
alongside voice in the normal application. No deployment is required.

## Design and implementation sequence

1. Review Tien's models, lifecycle, planner, turn storage and tests; run the unchanged baseline.
2. Reproduce and repair lifecycle/concurrent-create request-ID conflicts with regression tests.
3. Add an injectable Realtime credential provider and a session-scoped token route.
4. Generate frontend types from the updated OpenAPI contract.
5. Build a transport-independent transcript/progression adapter against failing tests.
6. Wrap it in browser WebRTC microphone/playback management with cleanup and connection tests.
7. Exercise the same components in a loopback-only development workbench.
8. Verify live model access, credential creation, native browser audio and the answer/tool path;
   preserve failures and reruns separately from offline regression results.

## Boundaries

- `backend/app/providers/realtime.py`: permanent-key boundary, frozen interview context, native
  audio session settings and the permitted voice tools. Requested model: `gpt-realtime-2`.
- `backend/app/api/realtime.py`: `POST /api/sessions/{session_id}/interviews/{id}/realtime-token`.
  Only active interviews receive credentials. Provider failure does not invalidate a working
  connection. Credentials are response-only and have `Cache-Control: no-store`.
- `frontend/src/voice/voiceSession.ts`: normalized app turn IDs, persistence queue, final
  transcription gating, tool dispatch, question progression, interruption and finish handling.
- `frontend/src/voice/controller.ts`: WebRTC, microphone permission, short-lived credential
  exchange, playback, mute, reconnect-by-explicit-connect and resource cleanup.
- `frontend/src/voice/interviewApi.ts` and `types.ts`: app API client and aliases to generated
  OpenAPI types, rather than another handwritten copy of the server's wire models.

The browser sends live audio directly to OpenAI. FastAPI keeps the permanent key and supplies
frozen context. The native voice model may propose a follow-up, but Tien's service alone issues
and identifies the next question. `continue_listening` and `repeat_question` do not advance it.
The application stores normalized text turns, not raw live microphone recordings.

## Local workbench

From this checkout, install dependencies as described in the root README, then run:

```bash
.venv/bin/python scripts/voice_dev_server.py --env-file /absolute/path/to/your/.env.local
```

In another terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --strictPort
```

Open <http://127.0.0.1:5173/voice-dev.html>.

The development API listens only on `127.0.0.1:8010`. Its separate `/api/voice-demo` endpoint
prepares Maya's supplied synthetic profile with a template question planner. That endpoint is
not part of the normal application. It avoids making additional profile/CV/planner calls while
testing native audio. Voice/transcription requests still use the real configured provider and
can incur charges.

Agree to audio/transcript use, prepare the synthetic demo and start voice. The interviewer
automatically speaks the first and every subsequent issued question; the displayed question
is a text backup, not a prompt the candidate needs to read or request aloud. Speech requests
wait until output playback is available. If autoplay is blocked, Enable audio resumes the
waiting question without advancing the interview or requiring a greeting.
Mute, Enable audio, Skip and Finish are explicit controls. Browser microphone denial
and connection failures are shown without leaking provider responses or credentials. Closing
or disconnecting releases tracks, playback and the peer connection.

For a genuine practice session, use your own confirmed profile through the regular app and
connect the controller to that interview; do not present the synthetic demo as your real CV.

## Mio's integration surface

```ts
import { RealtimeVoiceController } from './voice/controller'
import { interviewApi } from './voice/interviewApi'

const controller = new RealtimeVoiceController(interviewApi(session_id))
const unsubscribe = controller.subscribe((event) => {
  // Render connection/activity, transcript, issued question, safe error, or finished event.
})
await controller.connect(interview_id)
controller.set_muted(true)
await controller.resume_audio()
await controller.skip()
await controller.finish()
// On component unmount: unsubscribe(); controller.disconnect()
```

The calls above illustrate the separate available controls; a UI should invoke them only in
response to the appropriate user action, not execute the entire list in sequence. `connect`
starts a ready interview, or reloads/repeats the current question of an active interview.
`disconnect` closes local resources without claiming the interview completed. `finish` first
mutes input and drains registered transcripts before calling the end route.

## Review findings in Tien's PR

The original PR passed 269 backend tests, 29 frontend tests, Ruff, mypy, ESLint, frontend typing,
API contract checking and production build in the isolated checkout.

Two additional tests reproduced request-ID bugs, repaired locally here:

1. **Lifecycle action replay (P2):** calling `/cancel` using an already successful `/end`
   request's ID and identical payload returned the end response with HTTP 200. End/cancel have
   the same request model. Fingerprints now include the action, so this conflicts with 409.
2. **Concurrent create conflict (P2):** two concurrent creations with the same request ID but
   different config could both return the winning interview. The post-planning lock now repeats
   the input fingerprint check. A barrier-based test makes this race reproducible.

These are additional local fixes; this document is not an approval or merge of the upstream PR.

## Verification and limits

Offline tests use fake provider/transport boundaries and real application adapters. They do not
prove microphone quality or provider reliability. The actual live runs and failures are recorded
under `docs/evidence/a3_voice/`; Tien's live question-plan artifacts are retained separately under
`docs/evidence/a3_interview_flow/`.

Remaining product work includes Mio's final-screen integration, Sunny's feedback/metrics,
recorded-answer fallback, human microphone testing across devices, and broader live interruption
and reconnect trials. Reconnection is an explicit new connection and repeats the current issued
question; it is not a seamless restoration of the provider's previous audio context. A lost
unsaved transcript is surfaced as an error, never replaced with an invented answer.

Input transcription is an ASR approximation and can differ from the native model's interpretation.
Do not infer internal pauses, confidence, accent quality or employability from these transcripts.
Speech timings use provider audio clocks and are not API-event receipt timestamps. Spoken control
requests remain visible in the transcript; feedback must distinguish them from substantive answers.

## Voice/transcription refinement (22 October)

The conversation model remains `gpt-realtime-2`. The separate ASR default is now
`gpt-4o-transcribe`, with the interview's English language and a short, fixed technical glossary.
The glossary contains possible terms, not a candidate answer or copied job requirements.
No post-processing model rewrites answers. A clean synthetic comparison tied with the prior
mini model; the full model is a provisional quality-oriented default, not a demonstrated win
on Luke's voice. See the actual comparison and its limits in
`../evidence/a3_voice/2026-10-22-transcription-refinement.md`.

Backend settings (restart the backend after changing these):

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime-2` | Native conversation; unchanged |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-4o-transcribe` | Separate input transcription; mini remains configurable |
| `OPENAI_VOICE` | `marin` | `marin` or `cedar`; compare in separate sessions |
| `OPENAI_VOICE_SPEED` | `1.0` | Audio speed, validated from 0.25 to 1.5 |
| `OPENAI_INPUT_NOISE_REDUCTION` | `far_field` | Laptop/room microphone; use `near_field` for a close headset |

Semantic VAD remains `low` eagerness, with interruptions enabled. Both the session instructions
and each issued-question request specify warm, conversational delivery, natural emphasis and
short punctuation pauses without adding questions, answers or scoring. Changing voice requires
a new session after audio has already been produced.

The adapter now deduplicates provider event IDs and prevents late failures/conflicting completion
events from replacing a finalized transcript. Separate items retain separate app turn IDs and
their original VAD registration order even when final transcription completes out of order.
This does not guess missing timing or reorder raw provider events without evidence.

`TranscriptView` is a small workbench renderer: one stable row per turn, hidden empty pending
rows, explicit provisional/final labels, stale-revision rejection and plain-text rendering.
Only the affected caption is updated; previous rows are not recreated for every delta. Mio can
use the existing `transcript` and `activity` events in the final UI; no wire contract changed.

## State-driven voice orb (23 October)

The workbench now has a centred blue-white CSS orb, round mute/end controls, the current
question and the existing transcript below it. Mio's main React screens are unchanged.
`VoiceOrbView` maps existing controller events to idle, ready, connecting, listening,
interviewer-speaking, candidate-speaking, muted, error and finished states. Animations indicate
activity state, not measured microphone amplitude, confidence or emotion. Muted and terminal
states stop motion; `prefers-reduced-motion` disables all animation. Controls retain accessible
names, focus styles and a mute pressed state. Developer details remain collapsed by default.

Review also exposed and repaired control-path issues: channel loss and unrecoverable engine
errors now release the microphone and make reconnect available; mute preserves underlying
playback state; failed ASR attempts remain evidence without poisoning a successful retry;
Skip cancels/clears old speech and queues the next question until the old response ends.
Finalization mutes new input but keeps the channel alive for pending transcripts until the
backend reaches a terminal state. A finalizing end response is not reported as completed.

Same-page reconnect keeps existing transcript rows. Consumers mounting a fresh UI should load
saved turns from the interview GET response; the adapter does not add cross-reload session
discovery or seamless provider-context restoration.

## Feedback integration and startup ownership (24 October)

The normal application creates configured providers during FastAPI startup, not during imports
or OpenAPI export. Interview and realtime-token routes resolve the same live interview flow;
feedback uses that flow too. The native-voice provider shares the application-owned SDK client,
which is closed after feedback workers drain. Injected test services remain credential-free.
Callers injecting services must explicitly inject a configured realtime provider when needed.

The voice-only workbench does this explicitly. Its template planner and synthetic context are
unchanged, and it is still not an end-to-end generated-feedback demo. Use the normal API for
Sunny's feedback endpoints and Mio's eventual integrated UI. See
`../evidence/a3_voice/2026-10-24-integration-checks.md` for the reproduced startup failure.

## Sources

- [Realtime WebRTC](https://developers.openai.com/api/docs/guides/voice-webrtc)
- [Realtime conversations and tool responses](https://developers.openai.com/api/docs/guides/realtime-conversations#function-calling)
- [Realtime server events](https://developers.openai.com/api/reference/resources/realtime/server-events)
