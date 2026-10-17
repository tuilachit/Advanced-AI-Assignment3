# AI-Powered CV Builder Implementation Plan

**Goal:** Build a local React/FastAPI CV builder that collects and confirms profile facts, retrieves three supplied jobs, generates a job-specific CV with evidence links, validates every claim, and exports a PDF.

**Architecture:** React + TypeScript + Vite calls a Python 3.12 FastAPI API. The backend owns temporary UUID sessions, a guarded workflow state machine, retrieval over the nine supplied jobs, a bounded OpenAI Responses tool loop, structured CV generation, and provenance validation. The client owns the guided experience and local PDF rendering.

**Stack:** React, TypeScript, Vite, FastAPI, Pydantic, OpenAI Python SDK, pytest, Vitest, Playwright, and `@react-pdf/renderer`.

## Ordered delivery

1. Scaffold the repository, secure configuration, dependency locks and quality commands.
2. Test-drive profile facts, temporary sessions, state transitions and downstream invalidation.
3. Test-drive deterministic top-three retrieval with exact job excerpts and isolated match/eligibility language.
4. Add the provider boundary, fake provider and bounded Responses function-calling loop.
5. Add structured CV generation, fact references, validation and content-hash export gating.
6. Expose the approved FastAPI endpoints and consistent error contracts.
7. Build the Profile, Job matches, CV studio and Evidence stages in React.
8. Add validated PDF rendering and export recording.
9. Run the five supplied profiles, an unseen profile, isolation checks and a genuine failure/repair cycle; retain real evidence only.
10. Complete the README, architecture diagram, Prompt Record, report, demo checklist and submission packaging checks.

Each behavior follows red-green-refactor, and each checkpoint is committed separately. Live API evaluation begins only after deterministic offline tests pass.

