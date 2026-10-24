# Controlled headphone/speaker comparison — 24 October 2026

**Status: both tests completed. Test B reproduced provider VAD interruption while
the user was silent; Test A played fully. Speaker pickup is strongly supported,
but the exact acoustic input was not recorded.**
This is a diagnostic run of the unchanged application, not a proposed repair.
Branch `feature/interview-ui-integration`, commit `56ca40a`.

The [earlier failed run](2026-10-24-voice-interruption-investigation.md) and its
transcript/feedback remain preserved. Application source, provider configuration,
generated contracts and safety checks are unchanged. No commit, push or merge
was performed during the diagnostic comparison.

## Controlled input and test sequence

Prepared through the ordinary application UI using the same approved synthetic
Maya profile, entries and Graduate AI Engineer job description:

- Session: `87bbb5cd-8805-43bd-bef5-2ccfaf9882b3`.
- New interview: `interview-db288eaa-9bd2-427a-bfde-b947e034eb76`.
- Frozen context: `992a8cf971a94ac976ec9ae76301e2edb8908e4e3df97376796bb994ac76c1b4`.
- First question ID: `question-377f06b5-3922-4a4f-9ae0-ca9b9f6f55c5`.
- First question: “What interests you about starting your career as a Graduate AI
  Engineer, and how has your Computing Science degree prepared you to contribute
  to applied AI work?”
- Mixed, three main questions, up to one follow-up, English, optional CV omitted.
- A 15-minute server window permits changing devices between tests. Each listening
  sample covers only the first question plus five seconds of silence. The window
  is the only setup difference from the original five-minute failed interview;
  it is identical for both comparison conditions. No voice/VAD setting changed.
- Prepared phase `ready`, no started time, zero turns, no active microphone.

Test A uses headphones for output. Test B uses laptop speakers. Keep the Surface
stereo microphone, browser, input gain, audio enhancements, room and laptop
position unchanged. Record output volume separately for each output endpoint;
equal percentages do not guarantee equal acoustic loudness. Neither test mutes
the microphone during the measured question. The user stays silent throughout
the question and the following five seconds.

The initial device enumeration identifies
`Surfaceステレオマイク (2- Surface High Definition Audio)` and Surface Omnisonic
speaker output. For Test A the user confirmed Surface Stereo Microphone (Surface
High Definition Audio) as input, AirPods Pro #2 - Find My as output, and 68% Windows
output volume. A subsequent browser enumeration shows the default input as Surface
stereo microphone and default output as AirPods (Bluetooth); its communications
input is AirPods, so the actual acquired track still needs verification. The user
confirmed that the interview has not started. These settings were recorded in the
armed trial metadata. Actual track settings will be captured when the user starts
each test, without an extra microphone activation for setup.

Procedure:

1. Select headphone output, retaining the laptop microphone. Confirm microphone
   name and output volume; do not select a headset microphone automatically.
2. Arm `A_headphones` and let the user click **Start interview**. Stay silent,
   including greetings. If **Enable audio** appears, use it and record that fact.
3. After the question finishes, wait five seconds and click **Disconnect voice**.
   If it cuts off, stay silent for five seconds and disconnect if available. Stop
   after roughly 30 seconds if no question plays. Do not skip, answer, finish or
   reconnect yet. Report audibility, cutoff/error, any accidental speech and
   whether Enable audio was needed.
4. Review A's events and canonical snapshot. Verify the first question is still
   current, the interview is active, and the microphone track has ended. Save A's
   snapshot before B. If a false input advances the question or the timer expires,
   flag the condition and reassess; do not present a different question as a
   matched replay or alter saved state to force equivalence.
5. Select laptop-speaker output with the same microphone/input settings, confirm
   output volume, then arm `B_speakers`. The user clicks **Reconnect voice**.
   Luke's existing reconnect creates a new provider connection and repeats the
   same current issued question. Repeat the silence/disconnect procedure.
6. Compare effective microphone and session settings, question identity and
   response/playback events. Preserve both outcomes and human observations before
   considering any code change. End the diagnostic interview through the existing
   control after evidence capture if needed; do not regenerate feedback for this
   silent playback test as though it contained substantive answers.

## Recorder and evidence boundaries

Local helper files are under ignored `tmp/voice-comparison/`. `capture.cjs` attaches
to the already-open Chrome tab through local CDP and injects `observe.js` without
reload. It does not edit application files, stub a server/provider or call Luke's
private methods. It adds passive listeners and temporary wrappers around native
browser calls to record their timing while forwarding arguments/return values
and errors. It does not change microphone constraints, audio routing, VAD,
response requests, safety decisions or API request bodies. It can be detached
and its wrapped methods restored after the comparison.

Captured evidence:

- Client event timestamps use `performance.now()` and a fixed `timeOrigin`.
  Provider input-audio clock offsets are retained separately, not subtracted
  directly from client playback timestamps.
- Realtime event IDs, response/item IDs, question metadata, response status and
  cancellation reason; assistant item role/content types; outgoing response
  requests/cancels and audio clears; incoming VAD start/stop, audio buffer
  start/stop/clear, truncation, final ASR/output transcripts and safe error codes.
- Effective session model, voice/speed, VAD settings, transcription model/language
  and noise reduction, selected from `session.created`/`session.updated`.
- Microphone label, stable local device/group aliases and effective track settings
  (echo cancellation, noise suppression, gain control, sample rate where exposed).
- Audio-element play requests/results, playing/pause/waiting/stalled/error events
  and state; peer/channel connection changes; available aggregate audio RTP stats.
- Existing UI controls, connection/activity/error text, HTTP method/path/status
  for interview routes and canonical interview GET snapshots.

No raw audio, credentials, token-response bodies, headers, SDP, provider instruction
payloads or raw device IDs are retained. RTP receipt and `audio.playing` alone do
not prove human audibility. System-default sink routing and Windows volume require
operator confirmation; browser `audio.volume = 1` is not the Windows volume.

Events are flushed every second to `events.ndjson`; `capture-status.json` records
heartbeat, trial, dropped-event count and live-track count. Capture starts before
any microphone connection. `summarize.cjs` generates a chronological per-condition
summary relative to the captured native microphone request. The document-level
click listener missed Start because React changed the label before that listener
ran; the original summary incorrectly said `started: false`. Inspection of the
raw microphone/Realtime events established that capture was intact. Only the
offline summarizer was corrected to use `microphone.request` consistently for
both tests. No click timestamp was reconstructed and no application/recorder
behavior was changed between conditions. Source events remain intact.
Observe overhead exists; this is an instrumented run, not a recording of the
previous failure. One A/B pair can narrow the cause but cannot establish a
statistical echo-cancellation performance result.

The mock recorder check passed: installation makes no mic/play/send calls; native
arguments, return identity and call counts are preserved; message delivery reaches
the application; sensitive fields are excluded; restoration works. This validates
instrumentation behavior only, not real audio or the outcome of either condition.

## Interpretation to apply after both tests

| Observed sequence | Supported interpretation |
| --- | --- |
| VAD speech-start during playback while the user reports silence, followed by provider cancellation/clear/truncation | False speech detection interrupted playback; headphones reducing it supports acoustic pickup, but is not definitive proof of echo |
| Cutoff without preceding VAD/cancel/clear, with media error, stall or transport failure | Investigate playback/transport independently of ASR |
| Input ASR appears after false VAD with unrecognized words | Potential ASR artifact or captured external sound; do not label it verified human speech |
| Full output caption plus interrupted output buffer | Generated text completed, audible delivery did not necessarily complete |
| Unauthorized assistant item followed by client cancel/clear and controller failure | Authorization guard stopped the connection; distinguish this from provider VAD cancellation |
| Same failure with headphones and speakers | Echo alone is insufficient as an explanation; inspect common policy/event ordering and playback paths |

No fix will be inferred simply from success with headphones. If there is no
interruption in either sample, record non-reproduction rather than declaring the
original issue resolved. A silent first-question test also does not exercise the
substantive-answer/follow-up path that preceded the original authorization error.

## Separate issue for coordination with Luke

The unchanged adapter consumes its pending `speechPermit` on the next
`response.created`, without requiring matching question metadata. The earlier
offline replay demonstrated automatic-response permit consumption, acceptance of
mismatched question metadata, and rejection of a later legitimately issued
question. That is a separate confirmed code-level defect; its causal role in the
original live failure remains unconfirmed.

The `unissued_question` guard rejects an unmapped assistant output item before it
knows whether a question was audible. The controller then releases resources and
the UI displays `Connection lost`. Keep the guard and preserve this distinction.

Coordinate these findings with Luke before implementation:

- Review the captured outgoing request and incoming response metadata/order to
  identify which response was authorized and which item tripped the guard.
- Agree how automatic tool decisions and explicit issued-question speech are
  distinguished and how repeats/reconnects are correlated.
- Agree intended interruption policy during interviewer speech and the delivery
  events that should determine an interrupted transcript label.
- Agree regression expectations for false VAD, unsolicited output, pending
  transcription, resource cleanup and exactly-once question progression.

This records coordination topics, not an implemented fix or a message sent to
Luke. The existing cancellation/rejection checks remain unchanged.

## Results

| Condition | Hardware/settings verified | Human audibility | Event finding |
| --- | --- | --- | --- |
| A — headphones | Surface mic acquired; AirPods output / 68% confirmed by operator | Entire question clear; no cutoff; user silent | About 9.16 s playback; no VAD, input ASR, cancellation or error |
| B — laptop speakers | Same physical Surface mic and effective settings; Surface speakers / 68% confirmed | Cut off; user completely silent and denies the recognized sentence | VAD at about 1.84 s of playback, then provider clear/cancel (`turn_detected`); unexpected ASR afterward |

Do not claim either human test passed until its events and operator observations
have been reviewed together.

### Test A evidence

The user confirmed hearing the complete question clearly without interruption,
remaining silent throughout it and for five seconds afterward. The acquired
track was `Surfaceステレオマイク (2- Surface High Definition Audio)`, local device
alias `device-1`, group `device-2`. Effective settings were echo cancellation,
noise suppression and automatic gain control all enabled, mono, 48,000 Hz,
16-bit samples, reported latency 0.01 s. The input track was enabled and not muted.
AirPods output at 68% is operator-confirmed; the browser listed default output as
AirPods. The media element used the system-default sink and its own volume 1.

Effective Realtime settings matched the existing code: `gpt-realtime-2`, `marin`,
speed 1, semantic VAD with low eagerness, automatic response and interruption both
enabled, far-field noise reduction, English `gpt-4o-transcribe`, session tool
choice required. No setting was relaxed for this successful run.

Client-observed timeline, milliseconds relative to `microphone.request`:

| Event | Relative ms |
| --- | ---: |
| Surface microphone acquired | 31.1 |
| Media element playing; play promise resolved | 1,783.0 |
| Peer connected | 2,202.9 |
| Explicit issued-question response request | 2,604.3 |
| Response created with matching question metadata | 2,973.2 |
| Output audio buffer started | 3,403.3 |
| Response generation completed | 4,902.0 |
| Output audio buffer stopped normally | 12,567.8 |
| Audio paused by explicit disconnect cleanup | 24,872.9 |
| UI disconnected; Disconnect control observed | 24,876.7 |
| Data channel closed | 24,878.9 |

Thus the buffer-start-to-stop interval was 9,164.5 ms. Generation completed about
1,498.7 ms after buffer start, while audio continued for another 7,665.8 ms. This
directly distinguishes generated-caption/response completion from played audio.
One brief `audio.waiting` occurred during initial media setup before model output;
`audio.playing` followed immediately. There was no mid-question stall/error.

There were zero provider VAD speech-start/stop events, zero input-ASR events,
zero response cancels/audio clears and no `unissued_question` or transport failure.
The recorder reported zero dropped events and zero live microphone tracks after
disconnect. The response and question metadata matched:
`resp_EcSEDU5ZrFG499Bf1s3Un` and
`question-377f06b5-3922-4a4f-9ae0-ca9b9f6f55c5`.

The canonical interview remained active at flow revision 1/transcript revision 3,
with the same current first question, one final interviewer turn marked delivery
`complete`, and no candidate turns. The 15-minute clock started at
`2026-10-24T09:21:18.837444Z`; it continues while disconnected. B must start before
expiry and retain the same current question to count as the planned matched replay.

Frozen local A evidence: `tmp/voice-comparison/A-headphones-evidence/`, containing
the raw trial events, canonical interview, separate human observation and SHA-256
manifest. Interview snapshot hash:
`72952e5491bbbc0280a0025f70bd56e6606997450d32206e4c613af04098564c`.

Test A establishes successful real playback under the headphone condition and
silence, not that the original failure was definitely echo-related. It did not
exercise candidate-answer progression or reproduce the separate authorization
defect. The completed comparison follows.

### Test B evidence

The user confirmed Surface Omnisonic speakers at 68%, the unchanged Surface
microphone, complete silence, and a cutoff midway through the question. They
explicitly deny saying the displayed sentence `Which version of Python are you
using?` and report no page refresh or additional reconnect.

The acquired track is the same physical device/group (`device-1` / `device-2`)
and has **identical effective settings** to A, including echo cancellation, noise
suppression and gain control enabled, mono 48 kHz / 16-bit, latency 0.01 s. The
browser enumerated Surface Omnisonic as default output at connection. Effective
Realtime settings, question ID and the full generated question text also match A.
This is a valid replay of the same issued first question with a fresh provider
connection, without a question advance or changed voice policy.

Client-observed timeline, milliseconds relative to B's `microphone.request`:

| Event | Relative ms |
| --- | ---: |
| Media element playing; play promise resolved | 1,986.3–1,986.4 |
| Peer connected | 2,446.2 |
| Explicit issued-question response request | 2,835.8 |
| Response created with matching question metadata | 3,490.3 |
| Output audio buffer started | 3,593.6 |
| Full generated question transcript completed | 5,098.7 |
| Response generation completed | 5,103.7 |
| Provider `input_audio_buffer.speech_started` | 5,434.6 |
| Provider `output_audio_buffer.cleared` | 5,436.2 |
| Same response cancelled: `status_details.reason = turn_detected` | 5,436.5 |
| Provider truncation of interviewer item at output `audio_end_ms = 1820` | 5,438.5 |
| Provider speech-stop | 7,301.3 |
| Input committed | 7,304.9 |
| Automatic response created with empty question metadata | 7,319.6 |
| Input ASR completes: `Which version of Python are you using?` | 7,777.3 |
| Automatic response adds a `continue_listening` function call | 7,926.8 |
| Automatic function-only response completes | 7,957.1 |
| Explicit disconnect pauses media | 71,358.9 |
| UI disconnected; Disconnect control observed | 71,363.6 |
| Data channel closed | 71,366.6 |

The VAD start occurred **1,841.0 ms after output-buffer start**. The provider then
cleared the buffer 1.6 ms later and cancelled with reason `turn_detected`. No
outgoing client `response.cancel` or `output_audio_buffer.clear` preceded this;
there were none in B. The provider's 1,820 ms output truncation is consistent with
the roughly 1.84-second client-observed playback interval. These are different
clock observations, not a claim of sample-exact acoustic timing.

The unexpected ASR text arrived **2,341.1 ms after buffer clear**, so that text
cannot have directly caused the already-observed interruption. It belongs to the
same provider item as the VAD detection, `item_EcSIjY8RiBKbIrlzJ3tTa`, whose input
clock span is 2,220–3,280 ms. The cancelled interviewer response is
`resp_EcSIgEnofp4K3TOlQvO7k`; its item is `item_EcSIgqEFesI4tjQtdqdbh`.
The automatic function response is `resp_EcSIli8IKeAFND2v3aSFb`.

There was one startup `audio.waiting` followed immediately by playing, as in A;
no media error, rejected playback, mid-question stall or peer failure was recorded.
The media element remained unpaused and the connection remained up until explicit
Disconnect much later. Final available inbound RTP stats reported zero packets
lost. The explicit provider cancellation is the decisive evidence of the cutoff,
not merely an inference from missing audio or the UI's interrupted label.

The provider's final ASR event contains exactly the unexpected sentence. The app
persisted it as received, assigning the microphone input its existing `candidate`
label. The sentence is absent from the generated interviewer question and is
human-disputed, so do not describe it as a verified candidate answer or a verbatim
echo of the interviewer. Without source audio we cannot distinguish an ASR
hallucination over noise/echo from recognition of some other captured sound.

At capture completion, the canonical record remained `active`, flow revision 1,
transcript revision 10, on the same first question. It contains A's complete
interviewer turn, B's interrupted interviewer turn and the disputed input turn.
There was one new token POST and seven successful turn POSTs in B, **no next-step
POST**, and no second start. The original 15-minute server timer continues while
disconnected and can later finalize the interview; any later terminal state must
not be mistaken for a successful answered-interview test. No feedback was requested
for this silent comparison.

The trace contains zero observer errors, unparsed messages or reported dropped
events. Both microphone tracks were ended after disconnect; zero remained live.
The temporary browser wrappers/listeners were restored and the diagnostic helper
was stopped after recording the user's observation. Chrome and the application
servers were left running, with no refresh or new connection.

Frozen B evidence: `tmp/voice-comparison/B-speakers-evidence/`, with event trace,
canonical snapshot, human observation and SHA-256 manifest. Snapshot hash:
`d844f1baf4bab188e10bd7258628b741688658187d1e20f8907991524c2547fc`.
Raw event trace hash:
`bf428638674e0f901076f8247d5e9999d2072b4a02ed739da34c6c14448652e0`.
The original failed-run evidence and frozen A files remain unchanged.

### Findings from the completed comparison

1. **Confirmed proximate cause in B:** provider turn detection interrupted the
   audio. It is not simply an inaccurate caption or an independently failed
   browser playback path. Generated text/response completion preceded cancellation
   while output audio still had unplayed content.
2. **Strongly supported acoustic explanation:** with the same microphone,
   effective settings, question and reported silence, headphones produced no VAD
   events and full playback; laptop speakers produced an early input speech event
   and interruption. Speaker-to-microphone pickup triggering a false candidate
   turn is the leading explanation, even though echo cancellation was enabled.
   One ordered A/B pair without raw audio cannot prove the exact waveform source
   or establish the error rate across environments. Other acoustic false triggers
   remain possible. The original unrecorded run's exact cause is not retroactively
   proven by this reproduction.
3. **ASR is a separate, downstream issue:** the disputed sentence followed the
   interruption and was generated by provider input transcription. Keep it intact
   as diagnostic evidence, annotated here as not spoken by the user; do not use it
   as evidence of their skills, answer quality or intentional speaking metrics.
4. **No `unissued_question` in B:** the authorized question mapped correctly, then
   the automatic VAD response emitted only `continue_listening`. There was no
   uncorrelated assistant message, UI error, fatal guard shutdown or progression.
   This run reproduces the playback/false-input problem, not the later safety
   error from the first full attempt.

### Coordination with Luke before any repair

Share the measured VAD → provider clear → `turn_detected` cancellation sequence,
the same-device/settings comparison, and the separate ASR event timing. Review
the intended interruption policy for speaker playback, treatment of generated
text versus audible delivery, and how disputed/non-human microphone input should
be handled. The recorded completed-then-cancelled events for the same response
while its audio buffer is active deserve targeted regression coverage.

Keep the earlier authorization finding separate: pending question permission can
be consumed by an unrelated `response.created` in the offline reproduction. Luke
should review correlation and automatic-response ordering with those reproductions;
the successful function-only response in B neither reproduces nor disproves that
defect. Preserve the existing unissued-output rejection and resource cleanup.

These are findings and coordination topics only. During this comparison no fixes,
provider-setting changes, teammate core edits, commits, pushes or merges were
performed. No new
mocked test is being presented as a successful real microphone run. No additional
application regression suite was rerun because application source did not change.
