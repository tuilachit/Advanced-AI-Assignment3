# First human microphone run: interruption and response authorization

**Status: investigation only; no application fix implemented.** Human voice
playback/conversation acceptance failed. Successful ASR, one question advance and
a real feedback report are partial results, not a successful complete voice run.

Subsequent evidence: the [controlled headphone/speaker comparison](2026-10-24-controlled-voice-comparison.md)
captured a successful headphone replay and a speaker replay cancelled explicitly
by provider VAD (`turn_detected`) while the user was silent. The speaker replay
also produced a human-disputed ASR sentence after interruption. It did not
reproduce `unissued_question`. The findings below about the original run and its
missing raw trace remain historical; the new run supplies separate, stronger
evidence for the playback mechanism without proving the original event ordering.

Branch: `feature/interview-ui-integration`. Code: `56ca40a825ca79cacddb6fec95527b57634bcc51`.
During this investigation there were no application/test/configuration changes,
commits, pushes, merges or branch changes.
Luke's voice implementation and the original session were not modified.

## Observed run and preserved evidence

The user reported roughly 1–2 seconds of audible interviewer speech, successful
candidate transcription, a relevant follow-up, an interrupted interviewer caption,
then `The voice model spoke without an issued question. Reconnect to retry.` and
`Connection lost`.

Follow-up clarification: the user was using laptop speakers and does not remember
saying `All right`. They consider an ASR error or microphone pickup of the AI's
audio possible. They again reported that the audible question stopped after about
1–2 seconds even though the complete question was visible. Treat the disputed
phrase as unverified input ASR, not an established intentional acknowledgment.

- Session: `87bbb5cd-8805-43bd-bef5-2ccfaf9882b3`.
- Interview: `interview-1b882277-41b2-4d25-800f-184548214380`.
- Context: `71dca4a10259772c0de48551ae4a8e155cc8eaf0f43da2d474dbc4917ff03a0e`.
- Started 24 October 2026, 19:56:10 Sydney; ended 20:01:10 Sydney.
- Canonical phase `completed`, reason `time_limit`, flow revision 3, transcript
  revision 22. This is timer completion, not proof of successful manual finishing.
- Four planned/issued question records: the first main question answered, its
  follow-up issued without a submitted answer, two main questions not asked.

The backend/tab were not restarted or reloaded, no reconnect or microphone action
was triggered, and no API mutation was performed during this investigation.
Copies of existing snapshots/logs are in ignored
`tmp/phase3-live/incident-2026-10-24/`, with a SHA-256 manifest. Original files were
retained. No audio, credentials, token response, SDP or headers were copied.

Preserved completed snapshot SHA-256:
`1f8756eb0c1a6aa5738fcc5ef1f13d7263e126d3aec6bdd2dca7497560a13f90`.
The fresh read-only canonical snapshot has SHA-256
`69ed0d80a2f21035541da23d1b4b33d2628914fdba2a0ca9a04b5ed3ea5a93a4`.
Its only content difference from that completed snapshot is `feedback_status`,
which has since become `ready`; interview questions and turns match exactly.

### What the saved sequence establishes

These are canonical turn order and **provider input-audio clock intervals**, not
raw event arrival timestamps or offsets from interviewer playback start.

| Saved order | Result | Input audio interval |
| --- | --- | --- |
| First interviewer question | Full generated text matches the issued main question; final transcript, interrupted delivery | Not available |
| Input ASR labelled candidate; human source unverified | Final `All right`; user does not recall saying this | 2.380–3.640 seconds |
| Candidate short utterance | Final `UTS.` | 61.868–62.940 seconds |
| Candidate answer | Final `I'm interested in this role because I want to apply AI and machine learning to real-world problems.` | 75.980–82.960 seconds |
| Interviewer follow-up | Full generated text matches the issued follow-up about messy/incomplete data; final transcript, interrupted delivery | Not available |
| Candidate follow-up attempt | Empty, failed, transcript version 3 | 86.540–87.600 seconds |

The access log contains one successful start, one successful token request, 21
successful turn POSTs and one successful next-step POST. There is no skip or end
POST in that run. This supports working input transcription, persistence and one
backend-controlled progression; it gives no evidence of duplicate UI start/advance.

A full generated interviewer caption does **not** establish full audible delivery.
The adapter deliberately keeps interrupted delivery sticky even if a later final
transcript/output-stop event arrives. The last empty candidate turn also does not
prove a provider ASR error: backend drain expires pending turns to `failed` without
inventing text (`interview_flow.py:788–807`). Version 3 with both VAD timings is
consistent with a pending turn that lost its final event after disconnection.

### Evidence limits

The helper retained canonical API records, not Realtime data-channel events.
FastAPI's trace has profile/entry events only. There is no saved response ID,
metadata, output-item content type or cancellation reason for the failing message.
We cannot reconstruct the exact provider sequence or determine whether the early
speech detection was real candidate speech, speaker echo or environmental noise.
The user's laptop-speaker clarification makes acoustic pickup a stronger working
hypothesis, but there is no retained audio or event trace to establish its cause.

## Findings and ownership

### 1. VAD interruption is the leading explanation for the brief playback

`backend/app/providers/realtime.py:147–150` configures semantic VAD, low eagerness,
`create_response = true` and `interrupt_response = true`. The microphone is live
while questions play; the controller requests echo cancellation/noise suppression,
which does not establish that echo was absent in this environment.

OpenAI documents interruption on **speech start**, while semantic eagerness governs
the wait for the **end of candidate speech**. Low eagerness therefore does not
protect the interviewer from a short acknowledgment/false start. See
[VAD configuration](https://developers.openai.com/api/docs/guides/realtime-vad) and
[turn detection reference](https://developers.openai.com/api/reference/resources/realtime/client-events).

At `voiceSession.ts:140–147`, speech-start while an item is playing immediately
marks it interrupted and clears the local playing indicator. This explains the
state/caption change under the current policy. The saved early VAD turn and human
report support this mechanism, but do not prove acoustic cause or exact overlap.

### 1a. Follow-up investigation: playback and ASR are separate paths

The source separates three kinds of event:

- `input_audio_buffer.speech_started` marks local playback interrupted immediately,
  without waiting for or inspecting recognized words. The configured provider
  interruption policy can cancel/clear the actual output; the adapter's local
  indicator alone does not prove what the speaker played.
- `conversation.item.input_audio_transcription.*` stores recognized microphone
  text. Its completed/failed handler does not itself cancel or clear audio.
  `transcription_failed` is also absent from the controller's fatal-error list.
  Final ASR can unlock an already-pending tool advance; it does not independently
  decide that an answer is complete or issue another question.
- `response.output_audio_transcript.*` stores generated interviewer text. A final
  caption does not mean the output buffer has finished playing. The current
  adapter retains that text and the interrupted label rather than reconstructing
  which words reached the user's ears.

This distinction is consistent with the installed OpenAI SDK's
`ConversationItemInputAudioTranscriptionCompletedEvent` documentation: input ASR
is a separate asynchronous process from the native audio model. A wrong recognized
phrase is not proof that the voice model heard those same words. OpenAI also
documents provider-managed unplayed audio during WebRTC interruption in
[Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations#interruption-and-truncation).

An additional isolated replay of the unchanged adapter checked four cases:

| Injected condition | Observed adapter behavior |
| --- | --- |
| Input ASR completes with `All right`, without VAD or a pending advance tool | No interruption, cancel/clear or question progression |
| Input ASR fails, without VAD or a pending advance tool | `transcription_failed` reported; no interruption, cancel/clear or progression |
| Full generated question caption arrives while playback is active | Caption is final; playback remains active |
| VAD speech-start arrives before any recognized candidate words | Immediately marks interruption; a later full question caption and output-stop leave it interrupted |

All four diagnostic assertions passed. Script/results are ignored local artifacts:
`tmp/phase3-live/incident-2026-10-24/playback-transcription-diagnostic.mjs` and
`playback-transcription-diagnostic-results.json`. They simulate adapter inputs;
they neither exercise acoustic echo cancellation nor reproduce provider audio.

Updated assessment: a transcription error alone does not explain the observed
cutoff through these handlers. A common acoustic input could nevertheless cause
both false VAD interruption and erroneous ASR. Speaker pickup, other noise or
unremembered speech remain possibilities. Neither issued question contains the
words `All right`, so the text is not an exact echo match. ASR accuracy cannot be
determined retrospectively without the source audio. The `candidate` label is
assigned to microphone input by the adapter, not verified speaker identification.

The controller requests `echoCancellation: true` and `noiseSuppression: true`.
The failed run did not retain effective track settings or echo measurements, so
these requested constraints cannot establish successful cancellation. Do not
silently delete/relabel the canonical input turn or rewrite the feedback. The
existing speaking metrics include this ASR turn and therefore remain transcript
estimates, not verified measurements of only the human's intentional speech.

For a coordinated rerun, capture the redacted event trace before changing
behavior. Compare headphone output with the same laptop microphone and unchanged
voice settings against laptop-speaker output, remaining silent for the first
question in each fresh test interview. Record the selected input/output routes,
effective echo/noise settings, volume and human-observed audibility. Correlate VAD,
ASR item IDs, response cancellation/truncation, buffer events and audio-element
pause/error state. No VAD plus a cutoff would shift attention to playback/transport;
VAD while silent, reduced with headphones, would support acoustic pickup. Such a
comparison narrows the cause but one successful headphone run would not prove it.
Keep the failed interview unchanged. At this investigation checkpoint the rerun
was proposed, not started; its subsequent results are in the controlled
comparison linked at the top of this report.

### 2. Automatic responses and issued-question responses share fragile authorization

There are two response producers: VAD automatically requests a decision response;
`askCurrentQuestion()` explicitly requests audio for a backend-issued question.
Session defaults are audio plus `tool_choice: required`; the explicit question
overrides tool choice to `none` and supplies question metadata.

That per-response override does not itself change the session defaults. Required
tool choice should not be treated as an authorization to speak or proof that every
output item will be exclusively a function call. The API supports message/function
items and documents response metadata for correlation. See
[response creation reference](https://developers.openai.com/api/reference/resources/realtime/client-events).

**Confirmed defect:** `voiceSession.ts:116–123` consumes `speechPermit` on the next
`response.created`, regardless of which request caused it. Missing metadata falls
back to the pending question ID; supplied metadata is accepted without checking it
equals that permit. An automatic response can take the permit, a later legitimate
response can lose authorization, or unrelated output can inherit authorization.

An isolated offline replay imported the unchanged adapter with a fake persistence
API and fabricated provider events. It demonstrated:

| Diagnostic case | Current adapter result |
| --- | --- |
| Matching explicit question response | Correctly authorized |
| Automatic response arrives while question permission is pending, then the explicit response arrives | Explicit response rejected with `unissued_question` |
| Automatic assistant message arrives while permission is pending | Incorrectly accepted as the pending question |
| Response metadata identifies a different question | Attempts persistence under that different question ID |
| Unsolicited assistant message without a permit | Correctly rejected before persistence |

Replay: ignored `tmp/phase3-live/incident-2026-10-24/authorization-diagnostic.mjs`.
It does not call OpenAI, the browser, the live backend or the microphone. These
results prove adapter behavior for injected sequences, not that the live provider
produced that ordering. A concurrent default-conversation response may instead be
rejected by the provider. The fake persistence API does not prove the real backend
would accept a mismatched question ID.

### 3. What the reported error actually proves

`voiceSession.ts:125–134` rejects an assistant message item whose response ID has no
question mapping. It cancels that response, clears playback and emits the error.
It does not inspect the message wording or require audio to have begun. Therefore
the error proves **uncorrelated assistant output**, not that an invented question
was audibly delivered. An automatic response/preamble or incorrectly correlated
explicit response could both reach this guard.

Both saved interviewer turns were already mapped to issued questions. A plausible
sequence is early speech interrupts question 1; later the substantive answer and
tool advance succeed; speech interrupts the authorized follow-up; a subsequent
automatic response produces an uncorrelated assistant item and trips the guard.
This fits the saved evidence better than claiming that the saved follow-up itself
was never authorized. Its final response/item ordering remains unconfirmed.

`controller.ts:129–134` treats this error as fatal, releases mic/audio/WebRTC and
emits connection `failed`. `LiveInterviewStage.tsx:46` labels any such state
`Connection lost`. Thus the visible connection state is consistent with deliberate
guard-driven cleanup, without evidence of an initial network outage.

### 4. Scope: voice policy/adapter, with a UI wording limitation

The response generation, VAD policy, authorization map and shutdown are in Luke's
provider/voice implementation. `voiceBridge.ts` delegates to his controller;
`useLiveInterview.ts` observes events and polls GET snapshots. It has no raw
Realtime response-generation or question-authorization implementation. The two
polls do not issue duplicate questions, and this run has only one next-step POST.

No causal UI integration defect was found. The UI's generic `Connection lost`
label could distinguish a controller/protocol failure from transport loss later;
that wording change would not repair playback or authorization.

## Smallest safe proposed next work — coordinate with Luke first

1. **Fix the confirmed correlation defect in the existing adapter.** Bind a pending
   speech request to exact echoed metadata, including its question ID and a unique
   request identity for repeats. Consume permission only on a match; reject
   missing, mismatched, stale and duplicate identities. An automatic tool response
   must never take a speech permit. Keep cancellation, no unauthorized persistence
   and fatal handling for unissued assistant output. Use Realtime metadata, not a
   new handwritten backend/generated contract.
2. **Capture a minimal redacted event trace for a separate rerun.** Log direction,
   monotonic timestamp, event/response/item IDs, echoed request/question metadata,
   response status/cancellation reason, item type/role and playback/VAD events.
   Capture effective session VAD/tool/modality settings, using an allowlist rather
   than dumping session/token payloads. Exclude credentials, SDP and raw audio.
   This determines whether the incident is automatic assistant output, correlation
   loss or another sequence; the replay alone cannot choose between them.
3. **Agree on question-interruption policy.** For the MVP, propose allowing the
   interviewer to finish each issued question before accepting a conversational
   interruption, with explicit Skip/Finish still available. Simply toggling
   `interrupt_response` is incomplete: the adapter currently marks interruption on
   every speech start, and responses/answers arriving during playback need ordered
   handling. Base delivery state on actual playback/cancel events for the agreed
   policy; preserve candidate evidence rather than silently dropping it.
4. **If the trace confirms autonomous assistant output**, give the existing voice
   adapter sole response scheduling: keep VAD/transcription, disable automatic
   response generation, and explicitly request a non-audible tool decision for
   committed candidate input, serialized with issued-question playback. Reuse the
   current tools, final-ASR/save gating and backend next-step call. Do not just set
   `create_response = false`: that alone prevents the current automatic tools from
   driving progression. Unissued assistant output must still fail closed.

This is a staged proposal, not a claim that strict metadata alone resolves the
observed cutoff or every automatic response failure. The smallest proven repair
is correlation; a complete playback/conversation fix needs the event trace and
Luke's agreement on interruption/decision scheduling. No UI-side duplicate voice
engine, arbitrary delay, automatic retry loop or weakened guard is proposed.

## Targeted regression coverage for the coordinated patch

- Automatic tool response cannot consume a pending speech request; its correctly
  correlated question still plays exactly once.
- Missing/mismatched metadata, stale repeated-question requests, duplicate events
  and late old-connection responses cannot authorize output.
- Unissued assistant messages with empty initial content, text or audio still
  cancel/clear, never enter the authorized transcript, and trigger resource cleanup.
- Speech/acknowledgment during a question follows the agreed barge-in policy;
  generation completion is distinct from output-buffer playback completion.
- Any manual decision scheduler handles candidate input committed during playback,
  late/out-of-order ASR, continue/repeat/advance, and repeated VAD events without
  losing answers, overlapping responses or advancing twice.
- UI integration: correct error reason, microphone release, preserved transcript,
  explicit reconnect only, read-only polling and exactly one backend next-step.
- Real human rerun with event capture: full audible question, one substantive
  answer, one follow-up, controlled interruption/reconnect, completion and feedback.
  Keep this acceptance separate from mocked hardware and simulated previews.

Existing checks rerun against unchanged source: **80 frontend tests in five files
passed**, covering voice session/controller and Live Interview UI; **9 backend
Realtime tests passed**. The five offline diagnostics above also reproduced their
documented results. No new regression tests or fixes were added to the app. The
known backend retrieval checksum baseline remains unchanged and was not rerun.

## Feedback preserved as a separate partial success

The user subsequently generated a real feedback report through the application:
the access log has one feedback POST returning 202. The ready report was generated
at 20:03:30 Sydney. Its interview ID, context hash and transcript revision 22 match
the canonical completed interview. All four cited quotes are exact substrings of
the final candidate answer on the correct question. The UI displays the report,
unanswered follow-up and unavailable pause metric. No new feedback was requested
by the investigation, and no overall score or missing speech was invented.

This establishes feedback from the limited saved evidence, not a successful full
human voice interview. The original failure remains part of the presentation/test
record. Review and coordination with Luke are the next step before code changes.
