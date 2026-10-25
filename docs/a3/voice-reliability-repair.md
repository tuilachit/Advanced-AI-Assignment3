# Voice reliability repair — 25 October 2026

Branch: `codex/voice-reliability`, based on merged main `ddc5f35`.
This is an offline repair checkpoint, not live voice acceptance.

## Confirmed response-correlation bug

The previous adapter consumed its pending speech permission on whichever
`response.created` arrived next. Automatic VAD/tool responses could take permission
from an issued question. Missing metadata fell back to the pending question, while
different question metadata was trusted without checking it.

The repair binds each question/repeat request to the exact echoed `question_id`,
fresh `speech_request_id` and current `connection_id`. An unrelated response cannot
consume that permission. Duplicate response-created events cannot spend permission
for a later repeat. Delayed Skip cancellation is applied only to its matching speech
request. Unmapped assistant messages still trigger cancel/clear and the existing
fatal controller cleanup; the safety guard has not been weakened.

The backend API, generated API types, tools, question/progression ownership and
model (`gpt-realtime-2`) remain unchanged. Provider fixtures echo request metadata;
missing metadata is intentionally an invalid speech case.

## Approved finish-before-listen policy

Luke approved: “Yes—finish the question, then listen”. The outbound microphone
track is disabled as soon as it is acquired, before connecting to the provider.
Each issued question keeps input paused until its matching
`output_audio_buffer.stopped`, not merely `response.done` (generation completion).
The browser still owns an open microphone stream while the track is disabled;
the gate does not release hardware permission. Normal disconnect/failure cleanup
stops tracks and closes the connection.

- Manual mute is separate from automatic input protection. Unmuting during a
  question cannot bypass the gate, and a manually muted microphone remains muted
  after playback ends. Reconnect starts protected again.
- Provider VAD retains automatic tool decisions (`create_response=True`) but no
  longer automatically interrupts question speech (`interrupt_response=False`).
  Automatic responses default to text; only the explicit, correlated issued
  question request overrides the response to audio. Provider acceptance of this
  configuration still requires the authorized live test.
- Skip and Finish remain available. They explicitly stop playback; stale stop
  events cannot open the microphone for a later question. Blocked playback keeps
  input paused and uses the existing explicit Enable audio recovery.
- In-flight candidate transcripts remain evidence. They cannot cause advancement
  during protected playback. A newer repeat/listen decision supersedes an advance
  still waiting for final ASR without deleting saved transcript evidence. An
  already-submitted advance cannot be retracted by this local decision change.
- The ASR deadline is suspended while asking or queuing a question, including an
  already-running deadline. A separate 60-second speech watchdog fails closed and
  asks for reconnect if the provider never acknowledges/completes playback. This
  is a recovery deadline, not a fixed playback delay or automatic unmute.
- Unexpected question cancellation/clearing fails closed through existing fatal
  error cleanup. It does not silently enable input or automatically retry.
- Mio's layout, styles and controls are unchanged. The main UI and workbench add
  truthful “Preparing your question” / microphone-paused status text, and activity
  carries an optional `input_paused` flag. No backend contract changes are needed.

The stop event reports server output-buffer drain; it is not proof that a human
heard every word through their chosen speaker. Actual playback, echo performance
and transcription accuracy need controlled human acceptance.

## Evidence and verification

Six new cases were run against the old code and failed for the expected reasons:
automatic-response permit theft; missing/wrong-question/wrong-request/wrong-
connection metadata acceptance; and missing unique identity for repeated speech.
All six pass with the repair. Additional cases cover duplicate response creation
and Skip before creation with an intervening automatic response. New gating tests
were also observed failing before implementation (initial microphone protection,
generation versus playback completion, repeats, watchdog/cancellation cleanup and
truthful status). Review then found an already-armed ASR timeout during replay and
a preexisting stale advance decision after repeat/continue. Four focused cases
reproduced those failures before the fixes; all now pass. Follow-up read-only
review approved the revised repair with no further actionable findings.

- Backend: 561 tests pass, Ruff passes, mypy passes (32 files).
- Frontend: 190 unit/component tests pass; ESLint, API-contract check and
  TypeScript/production build pass.
- The first parallel browser run passed 34/36. Two separate scripted-preview
  timing assertions failed (`orb follows voice states...` and
  `cancelling a preview connection...`). Both passed three repeated isolated runs
  each, unchanged. The first failure stayed ready with a paused browser clock;
  the second had already passed its short connecting state. These failures are
  recorded, not described as repaired by the correlation change.
- The correlation-stage full single-worker browser rerun passed all 36 tests.
  No scripted-preview code was changed to achieve that result; the parallel
  timing failures remain a test-stability limitation, not a claimed repair.
- The protected-playback browser run passed all 36 tests, including the main UI's
  real controller over fake hardware, desktop/mobile layouts, transcript saving,
  disconnect/reconnect, feedback and CV export. The final full single-worker
  rerun after the four ASR/supersession regressions also passed all 36 (2.2m).

Tests use mocked HTTP/audio hardware; no live OpenAI call or real microphone
activation has been performed. Tests ran on a separate local frontend port, not
the user's running main checkout.

Reproduction commands from the repository root (all with `OPENAI_API_KEY=''`):
`.venv/bin/python -m pytest backend/tests`, `.venv/bin/ruff check backend`,
`npm --prefix frontend run test -- --run`, `npm --prefix frontend run lint`,
`npm --prefix frontend run build`, and `npm --prefix frontend run contract:check`.
Run `../.venv/bin/mypy app` from `backend/`. Browser coverage uses
`npm --prefix frontend run e2e -- --workers=1`; during this repair an untracked
temporary config changed only its base URL/server port to 5174 so port 5173 was
not reused. That temporary config was removed after verification.

## Pre-PR local handoff checkpoint

After verification, the owned local backend and frontend were restarted from
the repair worktree at ports 8000/5173 with `OPENAI_API_KEY=''`. Startup checks
returned API health 200, frontend 200 and session creation 201; the frontend
serves the repaired adapter source. A message request returned 503
`provider_unavailable`, confirming live-provider access remains disabled in this
runtime. Restarting cleared the former temporary in-memory sessions. At that
checkpoint, changes were local and uncommitted on `codex/voice-reliability`, with
no push, merge or deploy performed. Subsequent landing status belongs to the
GitHub PR rather than this historical checkpoint. The primary main checkout and
its untracked `docs/team/` were left untouched during the repair.

## Remaining live acceptance

The earlier controlled human run demonstrated provider VAD cancelling speaker
playback while the operator reported silence. Headphone playback completed.
See [the preserved comparison](../evidence/a3_ui/2026-10-24-controlled-voice-comparison.md).
The correlation fix does not repair acoustic echo or establish transcription
accuracy.

The approved protection is now implemented and offline-tested; this is not a
claim that the observed acoustic problem has passed a human rerun. Before live
testing, confirm that the previously exposed API key has been revoked/replaced;
do not reuse it merely because a local file exists. Then explicitly authorize
live calls and verify speaker and headphone playback, correct automatic first
and subsequent question speech, repeat, manual mute, Skip/Finish, transcript
accuracy, reconnect and saved transcript/feedback handoff. No paid provider call
or real microphone capture was made for this repair.

## Protocol references

- [OpenAI response creation](https://developers.openai.com/api/reference/resources/realtime/client-events#response.create):
  response metadata disambiguates responses, and inference settings override a
  single response rather than the whole session.
- [OpenAI VAD controls](https://developers.openai.com/api/docs/guides/realtime-conversations#keep-vad-but-disable-automatic-responses):
  automatic response creation and interruption are independent controls. Merely
  disabling automatic responses would break the current tool-decision path;
  that scheduling redesign is not part of this bounded patch.
- [Output buffer stopped](https://developers.openai.com/api/reference/resources/realtime/server-events#output_audio_buffer.stopped):
  WebRTC/SIP playback-buffer completion is distinct from generation completion,
  and identifies the response whose buffer drained.
