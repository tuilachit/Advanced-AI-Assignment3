# Acceptance Coverage Plan

**Goal:** Produce reproducible evidence that the current CV Builder meets the four requested engineering acceptance criteria without making live OpenAI calls.

**Global constraints:** Keep `.env.local` private; use fake or mocked providers in automated checks; do not weaken workflow or export gates; do not invent live evaluation evidence; keep work on `feat/ai-cv-builder`.

## Task 1: Baseline quality gates

Run all backend tests, Ruff, and strict mypy. Run frontend Vitest tests, ESLint, TypeScript checking, OpenAPI contract checking, and the production build. Record exact commands and outcomes in the task report. Do not change production code unless a failing check exposes a real defect.

## Task 2: Complete browser workflow coverage

Extend Playwright coverage for invalid actions, confirmed-profile revision and downstream invalidation, recoverable provider failure, independent browser sessions, and PDF export gating. Preserve the existing successful workflow. Exercise observable UI behavior rather than asserting only mocked call counts. Check profile, jobs, CV, and evidence stages at 1440px and 375px without horizontal overflow.

## Task 3: Complete evidence export-gate coverage

Add explicit backend service tests proving that an unsupported claim, a reference to a deleted fact, a fact belonging to another session, and an unconfirmed fact all prevent export. Assert the validation state/hash and that `record_export` rejects the CV. Reuse real workflow and CV service behavior; fake only the external model boundary.

## Task 4: Desktop and mobile interface review

Run the complete Playwright suite, capture the four workflow stages at 1440px and 375px, inspect the resulting screenshots for clipping, overlap, horizontal overflow, unreadable content, and error overlays, and record the observed result in `docs/evidence/04_System_Tests/acceptance_coverage.md`. Clearly distinguish automated mocked-browser evidence from pending live OpenAI evaluation.
