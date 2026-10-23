# Proposed title

feat(ui): add interview setup, live room and feedback review screens

# Proposed Draft PR body

## Summary

Evidence CV previously had no interview workspace. This change adds a responsive
Interview destination and a validated-CV handoff, with Setup connected to the
merged Interview Flow API. The Live Interview and Feedback screens provide the
UI boundaries for the remaining voice and evaluation integrations.

This is Mio's UI & Integration contribution. Real voice and feedback are not
connected in this PR: voice start stays unavailable in the main app, and sample
feedback is explicitly selected and clearly labelled. Existing CV save,
validation and PDF export logic is preserved.

## Completed features

- Interview navigation and **Practise interview** from an export-ready CV.
- Setup for matched/pasted jobs, optional validated CV, duration, question counts,
  focus and explicit audio/transcript consent. Uses the real create/read API,
  with loading/error handling, duplicate-submit protection and stable retry IDs.
- Live room with current question, main/follow-up progress, countdown, transcript,
  microphone/interview controls, connection/error/finalizing states and cleanup.
  A modular visualizer and controller boundary are ready for Luke's implementation.
- Feedback with completion summary, question-level criteria and STAR, exact
  transcript evidence, improvement suggestions and speaking metrics with explicit
  unavailable states. No overall score or substitution of missing values with zero.
- Actual interview summaries remain separate from fictional sample reports.
  Loading, error/retry, missing transcript and empty-interview states are covered.
- Responsive layouts, keyboard evidence navigation, reduced-motion support and
  separate development previews at `/interview-preview.html` and
  `/feedback-preview.html`. Preview pages are excluded from the normal build.

## Boundaries and dependencies

Feature code is contained in `frontend/src/features/interview/`, with small
navigation/API/type additions to the existing app. No backend, dataset, generated
schema, dependency or teammate core-logic changes are included. API records use
aliases to generated types; feedback view models are presentation models.

At review on 23 October 2026:

- [Luke's PR #2](https://github.com/tuilachit/Advanced-AI-Assignment3/pull/2) is
  open, non-draft and unmerged at `022a352`. After team integration, bind
  `RealtimeVoiceController(interviewApi(sessionId))` in `live/voiceBridge.ts`.
  Preserve controller ownership of audio, credentials, turns and progression.
- [Sunny's PR #3](https://github.com/tuilachit/Advanced-AI-Assignment3/pull/3) is
  an open draft at `179d2c9`. Models, metrics and job orchestration exist; HTTP
  routes, app wiring and generated frontend contracts are still pending. Add a
  generated-type client/source adapter once those are available, including
  read/start/poll, explicit failed-job retry and revision-conflict handling.
- The current UI changes have no file overlap with either PR at those heads.
  Coordinate polling ownership, canonical completed transcript revisions,
  submitted-answer/control-utterance handling and feedback retry/error semantics.

The implementation order is voice binding and combined controller tests, then
real feedback binding and tests, then a complete CV-to-interview-to-feedback
smoke test. Visual polish and advanced animation follow the working workflow.

## Verification

Fresh local results on 23 October 2026:

- ESLint, TypeScript and production build pass.
- **67 unit/component tests pass**: 29 existing, 9 Setup, 14 Live, 15 Feedback.
- **25 Chrome E2E tests pass**, including all 10 existing CV regressions plus
  15 Setup/Live/Feedback checks. PDF gates/downloads, profile invalidation,
  session isolation and navigation back to CV export remain covered.
- Backend-exported OpenAPI and regenerated TypeScript match the committed
  contracts using the Windows equivalent check with LF normalization; tracked
  generated files are unchanged. `git diff --check` passes.
- Responsive checks cover 1440, 768 and 375 pixels. Mock preview tests verify
  that no microphone or API/provider request is made.

These are deterministic UI/API-fixture tests, not evidence of integrated live
voice or real feedback generation. Earlier offline FastAPI setup smoke evidence
is recorded separately in `docs/a3/ui-integration.md`.

The pre-existing Windows backend baseline remains **268 passed, 1 failed** at
`test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid`, caused
by the raw-byte checksum difference from CRLF checkout of `data/jobs.jsonl`.
The full backend suite was not rerun for this review, and no unrelated fix is
included. Sessions remain temporary; interview refresh/history persistence is
outside this UI checkpoint.

See `docs/a3/integration-readiness.md` for the exact adapter files, owner contracts
and acceptance checks. Please review this as a **Draft** while integration remains
pending; no merge is requested.
