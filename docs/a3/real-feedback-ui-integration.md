# Phase 2B: Real Feedback UI integration — 24 October 2026

The main Feedback screen now consumes Sunny's merged feedback endpoints. This
work builds on the uncommitted Phase 2A voice integration on
`feature/interview-ui-integration`, at merge commit `4b006c4`. No commit, push,
merge, branch change, dependency installation or environment edit was performed.
Commits `51eb2bf` and `efbd501` remain intact.

## Ownership and contract

All additions belong to UI & Integration. Sunny's evaluator, provider, metrics,
job runner, routes and models, Luke's voice controller, Tien's flow, and generated
OpenAPI/TypeScript files are unchanged. Existing CV API methods are unchanged.

The shared `frontend/src/api.ts` client adds these existing routes, using the
same API root as the CV Builder and voice workflow:

| Operation | Existing contract | UI use |
| --- | --- | --- |
| GET `/api/sessions/{session_id}/interviews/{interview_id}/feedback` | `FeedbackResponse`: `not_requested`, `generating`, `ready`, `failed`; nullable report and nested error envelope | Read existing status on entry; poll every two seconds only while generating |
| POST to the same path | `FeedbackRequest`: `request_id`, `expected_transcript_revision`; HTTP 202 `FeedbackStartResponse` | Explicit **Generate feedback** or retryable **Retry generation** only |

`frontend/src/types.ts` aliases the existing generated schemas. There are no
manually defined wire DTOs. `feedbackService.ts` maps `FeedbackReport` into the
existing presentation models: `question_feedback` by question ID,
`technical_reasoning` to the technical-reasoning card, server applicability to
assessed/not-applicable/insufficient-evidence states, and the three speaking
metrics to their existing cards. Explanations, exact transcript quotes,
improvement suggestions, methods, coverage and limitations are retained.

The adapter computes no scores, eligibility or measurements. A genuine zero
remains zero; unavailable metrics and unassessed criteria remain unscored.
Malformed assessed scores or available measurements fail loading rather than
becoming zero. Existing quote validation still withholds an assessment whose
evidence cannot be matched to a final candidate turn for the correct question.
There is no overall score.

## Lifecycle and transcript identity

1. Live Interview hands off its completed canonical snapshot. Feedback makes no
   requests for ready, active, finalizing or cancelled interviews.
2. Opening feedback performs GET only, including under React StrictMode. An
   existing ready report displays immediately; no automatic generation occurs.
3. Explicit generation sends the expected final transcript revision and a UUID.
   Transcript text is never uploaded from the screen: Sunny's backend reads
   canonical final submitted answers and owns evaluation and deduplication.
4. A synchronous request guard prevents duplicate UI submissions. The request ID
   stays stable for retries of the same session/interview/context/revision while
   the screen is mounted. After remounting, GET checks the existing job first;
   backend evaluation-key deduplication remains authoritative.
5. POST returns `generating` even when reusing an already-ready result. The UI
   always follows it with GET. Polls are serial, with no overlapping reads, and
   stop on ready, failed or transport error. GET never starts or retries a job.
6. A failed job offers **Retry generation** only when the nested API error marks
   it retryable. A transport failure offers **Retry feedback**, which only reads
   status: an earlier POST may have reached the server. Raw provider/internal
   exception messages are not rendered.
7. A report must match interview ID, context hash and transcript revision before
   any assessment is displayed. Session ID is also part of the hook identity and
   endpoint. Identity changes abort in-flight work, hide the old report and
   ignore late responses. Revision/snapshot conflicts direct the user back to
   the interview, where the existing Live hook reloads the canonical snapshot;
   the next feedback handoff uses that refreshed snapshot. Expired interviews
   direct the user to setup instead of an endless retry.
8. Leaving feedback, selecting the sample, hiding the Interview stage through CV
   navigation or unmounting aborts client requests and clears polling timers.
   Aborting a browser request does not cancel an accepted backend job. Returning
   checks its status again. Live Interview is unmounted during Feedback, so
   Luke's voice poll is not running alongside feedback polling.

## Preview separation and review

The real screen binds a stable service source in `InterviewFeedback.tsx`.
**View sample feedback** explicitly switches to a different fictional interview
with its existing mock-data banner. It never evaluates or replaces the user's
interview and is never selected automatically after an API failure.

The standalone `feedback-preview.html` still makes no API requests.
`interview-preview.html` explicitly supplies a null service source, keeping
scripted interviews entirely disconnected from real feedback generation.
Existing cards, responsive CSS and Evidence CV styling are retained.

For review, complete an interview in the normal application and select
**View feedback → Generate feedback**. Check its questions, unavailable states,
evidence links and suggestions; **Back to interview** preserves the canonical
transcript. A regular backend on port 8000 with a locally configured key is
needed for a provider-backed run. It uses the existing `OPENAI_MODEL` setting
for feedback; no feedback-specific credential or new endpoint is required.
Temporary sessions and reports are still owned by the existing backend storage.

## Validation

- New `FeedbackApi.integration.test.tsx` exercises the actual wrapper, hook,
  adapter and shared HTTP client with HTTP mocked. Coverage includes StrictMode,
  explicit generation, duplicate action protection, cached ready reports,
  serial polling, job/transport retries, stable request IDs, stale reports,
  identity changes, insufficient evidence, genuine zero values, cancellation
  during POST/GET, hidden navigation and expired interviews.
- The focused Feedback suite passes **41 tests** (26 new API integration cases
  plus 15 existing presentation tests).
- All **33 Chrome E2E tests pass**. Two new cases cover explicit generation,
  asynchronous failure/retry, rendered API evidence, sample isolation, desktop
  and mobile widths, and stale-report recovery through a refreshed canonical
  interview. The existing real-controller browser test now continues through
  feedback generation using the final revision. CV workflow/export, Setup,
  Live preview, Feedback preview and Luke's workbench regressions still pass.
- Sunny's unchanged API/service/metrics/runtime suites pass **281 tests**:
  `python -m pytest backend/tests/test_interview_feedback_api.py
  backend/tests/test_interview_feedback.py backend/tests/test_feedback_metrics.py
  backend/tests/test_feedback_runtime.py -q`.
- Final full frontend suite: **166 tests pass in 13 files**, via
  `npm --prefix frontend test -- --run --maxWorkers=1`.
- ESLint, TypeScript and the production build pass via
  `npm --prefix frontend run lint`, `typecheck` and `build`. `git diff --check`
  passes. Scope review confirms no backend, voice core, generated schema,
  package/lockfile, environment or CV Builder component changes. Both existing
  feature commits remain ancestors of the unchanged branch HEAD.

Browser tests ran outside the Windows sandbox to allow temporary Vite cleanup.
HTTP, provider and microphone hardware were mocked in UI/browser tests; the
backend suites use their existing test providers. These results do not claim a
human microphone trial or live-provider feedback quality. Those are the next
reviewed workflow checks, not part of this automated phase.

The pre-existing full-backend checksum failure
`test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid` remains
documented in [ui-integration.md](ui-integration.md#existing-windows-test-baseline).
It was not changed or rerun in this feedback-focused backend check.
