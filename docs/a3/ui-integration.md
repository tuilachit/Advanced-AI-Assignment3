# Assignment 3: Interview UI integration

The next checkpoint prepares the UI for real voice without enabling audio:
[Real Voice Integration preparation](voice-ui-preparation.md).

For the current review across all three phases, see
[integration readiness](integration-readiness.md) and the
[proposed Draft PR](ui-draft-pr.md). The checkpoints below retain their original
scope and evidence; later sections supersede earlier plans for future screens.

## Phase 1A review checkpoint — 23 October 2026

This initial checkpoint implemented navigation and Interview Setup on
`feature/interview-ui-integration`. Live Interview and Feedback remain future
steps. No voice recording, interview start, or feedback request occurs here.

### Reviewing locally

With the API on port 8000 and Vite on port 5173, open
<http://127.0.0.1:5173> and choose **Interview**. The screen is accessible before
profile completion so its prerequisites are visible. A validated, saved CV also
offers **Practise interview** in CV studio.

Preparing an interview requires a confirmed profile, approved resume entries,
a matched or pasted job, and both consent checkboxes. A currently validated CV
is optional. Setup supports focus, duration, main-question count and follow-ups.
Success displays the returned interview summary while leaving its phase `ready`.
The existing CV workflow and export validation rules are preserved.

For real provider requests, supply your own `OPENAI_API_KEY` in the ignored
project-root `.env.local`. The key is never sent to the browser. No live provider
key was configured for this checkpoint, so live question generation is unverified.

### UI and API boundaries

- `frontend/src/components/StageNav.tsx`, `App.tsx` and `CVStage.tsx` provide the
  navigation and validated-CV handoff. Setup remains mounted across stage changes
  to retain the form and the most recently prepared interview during the session.
- `frontend/src/features/interview/InterviewSetupStage.tsx` renders readiness and
  the prepared summary; `InterviewSetupForm.tsx` owns form presentation.
- `setup.ts` derives defaults, readiness and payloads from the current session.
  `useInterviewSetup.ts` owns creation, errors, duplicate-submit protection and
  retry identity. An unchanged failed request retains its `request_id`; changed
  settings use a new ID.
- Session context changes reset the editing defaults and consent. An already
  prepared interview retains its original context and shows an explanatory notice.
  Page-refresh persistence is outside this checkpoint.
- `interview.css` reuses Evidence CV colours, typography, cards, buttons and status
  styles, with scoped desktop and mobile layouts. Presentation is separate from
  request handling so later visual changes can remain local.
- `frontend/src/api.ts` calls Tien's merged
  `POST /api/sessions/{session_id}/interviews`. Types in `types.ts` are aliases of
  the existing generated schema; generated files and backend contracts are unchanged.

The next step is a separate Live Interview view consuming the returned interview
and Luke's Voice Controller when available on this branch. Connection, microphone,
speaker and future avatar/orb presentation should subscribe to that controller;
the UI should not reimplement voice or backend progression logic. Feedback remains
a later view with explicitly labelled mock data until Sunny's API is available.

### Verification and evidence

The frontend checks are `npm --prefix frontend run lint`,
`npm --prefix frontend run build`, `npm --prefix frontend test -- --run` and
`npm --prefix frontend run e2e`. Build includes TypeScript checking.

- 38 unit/component tests pass, including nine Interview Setup tests.
- 14 Playwright tests pass, including four new navigation/setup tests and the
  existing CV workflow regressions. These browser tests use synthetic API fixtures.
- All 51 existing tests in `backend/tests/test_interview_flow.py` pass unchanged.
- A separate local browser-to-FastAPI smoke check used existing offline test
  providers and `TemplateQuestionPlanner`. Actual creation endpoints returned
  HTTP 201 and phase `ready` for a supplied job with a validated CV (four questions)
  and a pasted job without a CV (three questions). This is offline integration
  evidence, not live model or voice evidence.
- The smoke check recorded no microphone requests, no interview-start requests,
  no browser errors and no horizontal overflow at 1440, 768 and 375 pixels.

Local review screenshots are under the ignored `artifacts/generated/` directory:
`a3-ui-setup-offline-1440.png`, `a3-ui-setup-offline-768.png`,
`a3-ui-setup-offline-375.png` and `a3-ui-prepared-offline.png`. They show synthetic
candidate data with the offline planner. The local smoke result is
`tmp/dev/setup-verification.json`; these local artifacts are not committed evidence.

## Phase 1B: Live Interview UI — 23 October 2026

The live room is now reachable through **Interview → Prepare interview → Open
interview room**. It shows the job, current issued question, main-question progress,
countdown, transcript and voice controls. Feedback remains outside this checkpoint.

### Reviewing the live states

Open <http://127.0.0.1:5173/interview-preview.html> for the standalone local preview.
Choose **Start interview** to see scripted speaking, provisional captions, final
transcripts and listening. Try mute, skip, disconnect/reconnect, and end/confirm.
The expandable preview controls simulate connection loss, denied microphone access
and blocked playback. These are synthetic UI scenarios: **no microphone access,
provider requests, real voice, or saved interview**. The preview is separate from
the CV Builder and is not included in the normal production build.

In the normal application, the room reads the real interview through the existing
GET endpoint. Voice start is explicitly unavailable until Luke's modules can be
bound on this branch. A successful question-plan request is not evidence of a
working audio connection. No simulated transcript is inserted into a real session.

### Ownership and future wiring

All live UI code is under `frontend/src/features/interview/live/`:

| File | Responsibility |
| --- | --- |
| `LiveInterviewStage.tsx` | Layout, question/progress, countdown, controls, finish confirmation |
| `useLiveInterview.ts` | Controller subscription and command delegation, read-only status refresh, cleanup |
| `liveState.ts` | Display reconciliation, stale-event protection and remaining-time calculation |
| `InterviewTranscript.tsx` | Plain-text captions, provisional/final/failed labels and optional follow-latest scrolling |
| `InterviewerVisualizer.tsx` | Presentation-only orb placeholder and accessible state descriptions |
| `voiceBridge.ts` | Local UI port and the single future controller binding point |
| `liveInterview.css` | Scoped responsive presentation and reduced-motion support |

The bridge was checked against `origin/codex/voice-integration` at `022a352`.
Its methods and notifications structurally match Luke's `RealtimeVoiceController`.
`Interview`, questions and turns remain aliases to the generated API schema. The
UI adds no WebRTC, credentials, audio capture, turn persistence or question-selection
implementation, and does not post to start/next-step/skip/end itself.

Once Luke's modules are available through the team's normal integration process,
the binding in `voiceBridge.ts` can construct:

```ts
new RealtimeVoiceController(interviewApi(sessionId))
```

Use the imports from his `voice/controller.ts` and `voice/interviewApi.ts`; do not
copy those files. `VoiceIntegration.Visualizer` accepts a React component receiving
the visual state, interview and controller. It can wrap Luke's DOM `VoiceOrbView`
with refs/subscription cleanup, or host a later avatar, without changing session
logic. The current orb indicates activity state only, not measured audio amplitude.

### Behaviour worth checking

- Start is explicit. The controller owns microphone permission and starting a ready
  interview. A fresh controller must reconnect before controls can end an already
  active interview; its interview selection happens inside `connect()`.
- Remaining time derives from backend `started_at` and configured duration, rather
  than decrementing a counter. It keeps running while muted/disconnected. At zero,
  controls stop accepting answers and the UI waits for backend completion; it never
  sends a local timeout-driven finish request. The local clock should be accurate.
- Read-only GET refreshes recover saved turns and server status. Issued question
  events never advance the plan locally. Follow-ups retain their parent's main
  question number. Lower revisions cannot roll progress back.
- Final captions survive stale partial events and reconnects. Failed transcription
  and interrupted delivery are labelled; missing speech is not fabricated. Scrolling
  back disables follow-latest until the reader returns to the bottom or chooses it.
- Finish requires an inline confirmation. `finalizing` remains distinct from
  `completed`, so pending transcription is not presented as already complete.
- Leaving the room, switching CV stages, unmounting or closing the page disconnects
  the controller. Leaving does not finish the interview or pause its server deadline.
  Returning never starts recording automatically. Full-page session recovery remains
  outside this checkpoint, as in the original CV Builder.

### Phase 1B validation

- Lint and TypeScript/production build pass.
- 51 unit/component tests pass, including 13 live-screen tests covering controller
  events, microphone denial, playback recovery, caption reconciliation, follow-ups,
  confirmation/drain, timer expiry, stale API responses and navigation cleanup.
- 19 Chrome/Playwright tests pass: five live-screen checks plus the existing setup
  and CV regressions. Browser tests use fixtures or the explicitly simulated preview.
- All 51 unchanged backend interview-flow tests pass. The Windows full-suite
  baseline below remains documented and unfixed.
- Browser review covers 1440, 768 and 375 pixels with no horizontal overflow,
  plus reduced-motion preference. Preview checks reject microphone access and
  verify that no API/provider requests were made.
- Actual voice transport, microphone quality and live provider behaviour remain
  unverified here; they require Luke's integration and a configured provider.

Playwright screenshots are local artifacts in `frontend/test-results/`. Review
copies are in the ignored `artifacts/generated/a3-ui-live-preview-*.png` files;
these show simulated UI states and are not live voice evidence.

## Phase 1C: Feedback UI — 23 October 2026

### Review paths and data provenance

Open <http://127.0.0.1:5173/feedback-preview.html> to review the complete sample.
Its scenario selector covers successful loading, an error followed by retry,
continued loading, missing transcription and an interview with no asked questions.
The preview uses synthetic data and makes no API, provider or microphone requests.

The normal flow now offers **View feedback** only after the backend reports
`completed`. It first shows that interview's actual completion summary and explains
that the feedback service is not connected. **View sample feedback** explicitly
opens a separate fictional interview/report. Returning restores the original
summary. Sample scores are never assigned to the user's interview, and neither
the CV nor the saved interview is changed.

The Live Interview development preview follows the same navigation after finish;
its completion summary remains labelled as simulated. The sample-feedback banner
also stays visible during loading, errors and empty states.

### Reference model and display decisions

Reviewed Sunny's PR #3 branch `origin/feat/interview-feedback-evaluation` at
`179d2c9`, specifically `backend/app/domain/feedback_models.py`,
`providers/interview_feedback.py`, `services/interview_feedback.py` and
`services/feedback_metrics.py`. That revision has models/provider/service/job
orchestration, but no feedback routes or generated frontend feedback types.
No teammate files or branches were copied, edited or merged.

- Relevance, specificity, structure, technical reasoning and STAR are shown as
  individual 0–4 criteria. The score anchors follow Sunny's provider instructions.
  STAR is one criterion covering Situation, Task, Action and Result; the UI does
  not invent separate S/T/A/R scores or an overall score/percentage.
- `assessed`, `not_applicable` and `insufficient_evidence` remain distinct. An
  actual zero rating is supported; missing evidence never becomes a zero.
  The sample follows the service's category-based STAR/technical-reasoning policy.
- Main questions and follow-ups have separate reviews. Skipped questions retain
  insufficient-evidence states. Planned, unasked questions are listed without
  assessments. Completion counts and elapsed time come from the displayed
  interview, not from an aggregate evaluation score.
- Speaking pace, transcript fillers and pauses are per-question measurements.
  Available values retain their units, including a genuine zero filler count.
  Unavailable values show a reason instead of a number; method/coverage details
  remain accessible. No client-side speech analysis or cross-question average is
  implemented. Pauses are not inferred from transcript punctuation or arrival times.
- Quotes link to the corresponding full final candidate answer. Rendering checks
  turn ownership, question identity and an exact substring before displaying an
  assessed score. A missing/mismatched quote suppresses that score. This is a
  display guard, not a replacement for Sunny's evidence validation or assessment.
- Specific suggestions appear with their criterion. They ask for missing detail
  without fabricating outcomes, credentials or measurements.

### Files and integration boundary

All new feedback code is in `frontend/src/features/interview/feedback/`:

| File | Responsibility |
| --- | --- |
| `InterviewFeedback.tsx` | Actual-summary route and explicit sample selection |
| `FeedbackStage.tsx` | Screen composition, lifecycle states, rubric and limitations |
| `InterviewSummary.tsx` | Completion metadata, elapsed time and question counts |
| `QuestionFeedbackCard.tsx` | Expandable main/follow-up reviews |
| `CriteriaFeedback.tsx` | Criterion ratings, quotes and improvement suggestions |
| `SpeakingMetrics.tsx` | Values, unavailable reasons and method/coverage |
| `TranscriptEvidence.tsx` | Full-answer display and accessible quote navigation |
| `feedbackView.ts` | UI presentation models and report/evidence display guards |
| `useFeedback.ts` | Loading, retry, cancellation and stale-result protection |
| `sampleFeedback.ts` | Explicit synthetic interview/report and mock source |
| `feedback.css` | Scoped responsive styling and reduced-motion support |
| `preview.tsx` | Standalone development scenarios |

`feedbackView.ts` is a presentation model rather than a manually duplicated wire
schema. The generated API files are unchanged. When Sunny's routes are integrated,
generate the API aliases through the team's existing process and implement a
`FeedbackSource` adapter at `InterviewFeedback.tsx`. The adapter should own request
IDs, API start/poll/retry semantics and mapping into the view model:

| Sunny's model | Presentation mapping |
| --- | --- |
| `FeedbackReport` identity/context/transcript revision | Reject reports for a different snapshot |
| `question_feedback` | `questions`, joined to the existing interview questions |
| `CriterionFeedback.criterion` | Criterion key; `technical_reasoning` becomes `technicalReasoning` |
| `applicability` and nullable `score` | Discriminated rating with a numeric score only when assessed |
| `EvidenceQuote.turn_id` / `quote` | `turnId` / `excerpt`, linked to the full answer |
| `SpeakingMetric` status/value/unit/reason/method/turn IDs | Measurement value or unavailable reason, retaining method and coverage |
| Report generation time, rubric version, limitations | Report metadata and limitations |

`FeedbackSource.load()` receives an abort signal and returns the final view model.
The UI does not guess API URLs, start feedback on incomplete interviews, compute
scores, or implement Sunny's job orchestration. A failed load has an explicit
retry; leaving or changing the source cancels the old request. Context/revision
mismatches are surfaced rather than rendering stale feedback.

### Phase 1C verification

- Lint and TypeScript/production build pass.
- **67 frontend tests pass**, including 15 feedback tests and a live-to-feedback
  completion guard test. Coverage includes valid zero values, insufficient evidence,
  non-applicable STAR, quote ownership/plain-text rendering, unavailable metrics,
  loading/retry/cancellation, stale responses and sample/context separation.
- **25 Chrome/Playwright tests pass**, including six new feedback checks and all
  existing CV, Setup and Live Interview regressions. Review includes 1440, 768 and
  375 pixel widths with no horizontal overflow, keyboard accordion navigation,
  quote-to-answer focus and round-trip navigation back to the CV Builder.
- Mock preview checks confirm no microphone, API or provider calls. This is UI
  evidence, not a live feedback evaluation. No new dependencies were installed.
- Local screenshots are in `frontend/test-results/`; review copies are under the
  ignored `artifacts/generated/a3-ui-feedback-*.png` paths. They show mock data.
- Backend logic, generated API files and dataset files remain unchanged. The
  existing Windows backend test baseline below remains documented and unfixed.

## Existing Windows test baseline

The environment setup run of
`.venv\Scripts\python.exe -X utf8 -m pytest backend/tests` recorded **268 passed,
1 failed** before these UI changes. The remaining failure is
`backend/tests/test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid`.

This checkout has `core.autocrlf=true`, so `data/jobs.jsonl` has CRLF line endings.
Its raw-byte checksum differs from the committed embedding baseline; normalizing
the same content to LF reproduces the expected checksum. This is retained as a
baseline issue. Dataset files, frozen embeddings, Git line-ending configuration
and retrieval code have not been changed to make the test pass.

Use Python's `-X utf8` flag for the Windows test run: without it, this machine's
default cp932 encoding also causes an existing UTF-8 document-read failure.
