# Acceptance Coverage

## Scope and method

On 2026-09-07 (AEST), the complete frontend Playwright suite was run from `frontend/` with `npm run e2e`. It started the local Vite development runtime and completed all eight browser scenarios:

1. rejected export authorization preventing a PDF download;
2. long-headline visibility at desktop and phone widths;
3. rejection of foreign session IDs and incorrect HTTP methods by the mock API;
4. guided workflow completion, PDF export, section editing, and export re-lock after an edit;
5. confirmed-profile revision invalidating the stale jobs and CV workflow;
6. a committed profile update followed by provider failure removing the stale CV and recovering;
7. isolation of two independent browser workspaces; and
8. recoverable provider failure without losing the current session.

Playwright reported `8 passed (23.6s)` with exit status 0. The successful workflow re-created the eight stage screenshots below, using full-page captures at 1440 px and 375 px. These eight files are retained in Git as the reproducible visual evidence for this review.

| Stage | 1440 px capture | 375 px capture | Observed result |
| --- | --- | --- | --- |
| Profile | `artifacts/generated/redesign-profile-1440.png` (1440 x 1376) | `artifacts/generated/redesign-profile-375.png` (375 x 1745) | Landing/profile form, facts panel, navigation, and footer are legible; no clipping, overlap, horizontal overflow, or error overlay observed. |
| Jobs | `artifacts/generated/redesign-jobs-1440.png` (1440 x 1080) | `artifacts/generated/redesign-jobs-375.png` (375 x 2369) | Three job cards are readable. Desktop uses three columns; mobile stacks them vertically without clipping, overlap, horizontal overflow, or error overlay. |
| CV | `artifacts/generated/redesign-cv-1440.png` (1440 x 1140) | `artifacts/generated/redesign-cv-375.png` (375 x 1347) | Headline and section claims, validation action, and locked PDF panel are legible. At 375 px the professional headline grows to show its full value; no clipping, overlap, horizontal overflow, or error overlay observed. |
| Evidence | `artifacts/generated/redesign-evidence-1440.png` (1440 x 1414) | `artifacts/generated/redesign-evidence-375.png` (375 x 1938) | Fact statuses, headline and claim mappings, and tool/decision trace are readable. Mobile stacks panels cleanly; no clipping, overlap, horizontal overflow, or error overlay observed. |

The browser assertions also require the four stage buttons to exist and explicitly check `document.documentElement.scrollWidth <= innerWidth` at both capture widths. The mobile CV assertion confirms that the professional headline is a textarea and its `scrollHeight` does not exceed its `clientHeight`, preventing hidden vertical content. The visible stage headings and controls in every fresh capture establish that the development page rendered nonblank. Inspection of all eight captures found no Vite error overlay.

## Evidence-aware retrieval offline coverage

The 2026-09-09 evidence-aware retrieval gate is designed to run without an API key, provider
request or network retrieval. Its backend coverage validates the immutable six-profile baseline
and corpus hash, the fixed-vector reranking comparison, evidence scoring and explanations,
retrieval/API contracts, and the explicit offline evidence wording. Ruff and strict mypy cover
the backend and baseline verifier. The frontend contract check, Vitest suite, ESLint, TypeScript
check, production build and all eight mocked Playwright workflows cover the generated score
breakdown and its user-facing relevance explanation.

The fresh no-provider run passed 135 backend tests, Ruff, and strict mypy over 17 source files.
The generated API contract matched, all 12 Vitest tests passed, ESLint and the TypeScript check
passed, the production frontend built, and all eight mocked Playwright workflows passed in
21.7 seconds. `git diff --check` also passed. The commands contained no provider runner or live
retrieval step.

This coverage can establish deterministic behavior and regression protection only. The
fixed-vector comparison supplies synthetic values for historically unobserved fourth-to-ninth
positions, and the browser suite uses controlled API fixtures. Neither is a post-reranker live
evaluation. A separate billable rerun requires new user approval and must preserve the original
2026-09-07 artifacts while recording the reranker as a distinct configuration.

## Resume-entry review verification (2026-09-09 AEST)

The worktree was clean at `af34678` before this fresh verification. The backend suite passed
205 tests in 1.99 seconds; Ruff passed and mypy reported no issues in 17 source files. The
frontend generated-contract check matched, all 28 Vitest tests across three files passed,
and lint, typecheck and the production build passed.

The initial default browser command reused an existing main-checkout Vite server on port
5173 because the committed Playwright configuration permits reuse. Its page snapshot showed
the previous four-stage UI. Two tests timed out waiting for `Create resume entries`; the third
was interrupted and seven did not run. No application defect was inferred from that run.
The existing server was left running. The complete suite was rerun with a temporary worktree
configuration on port 5197, `--strictPort` and `reuseExistingServer: false`; all ten scenarios
passed in 38.3 seconds. The temporary configuration was removed after the run. For subsequent
worktree checks, use an isolated server and base URL rather than reusing an unrelated checkout.

| Requirement | Fresh verification and boundary |
| --- | --- |
| Separate resume-entry review stage | Browser flow creates proposed wording after profile confirmation, displays the original source text, edits heading/bullet wording, saves, and approves explicitly. Dirty text cannot be approved; jobs remain locked until a substantive entry is approved. Deleting the last entry locks jobs again. |
| Deterministic provenance gate | Backend tests reject missing, foreign, draft or unconfirmed fact citations; require per-item provenance and the exact source union; and verify that failed proposal/audit operations do not partially mutate the session. Deterministic guards run before semantic provider checks. |
| Restricted CV evidence | Backend coverage requires approved-entry provenance and confirmed contact facts for candidate content. Provider-boundary tests check instructions and structured payloads; they do not prove live model adherence. |
| Profile-revision invalidation | Browser coverage revises a profile after a validated CV exists, removes stale jobs/CV/PDF access and exposes linked entries as needing review. Reconfirming the profile alone does not restore job access; the wording must be reviewed, saved and approved again. |
| Sequential two-job behavior | One approved synthetic profile selects `graduate_ai_engineer`, generates/validates/downloads its CV, then selects `rag_agent_engineer`. Selecting the second job removes the old CV and export state. Its distinct CV remains locked until separately validated, and the second download uses that CV's own export route. These document IDs are controlled browser fixtures, not live retrieval selections. |
| Evidence audit and student-facing screens | Mocked browser assertions retain entry IDs, fact sources and job IDs in Evidence while standard profile/review/jobs/CV screens hide those raw identifiers. |
| Provider failure and session isolation | Mocked failures preserve the committed revised fact while removing stale CV access, then recover through explicit review. Independent browser contexts retain their own facts, proposed entries, approvals and audit identifiers. |
| PDF locking | Browser tests cover unvalidated/edited drafts, job/profile changes and rejected export authorization; a rejected export does not start a download. |
| Desktop/mobile behavior | Fresh assertions pass at 1440 px and 375 px across profile, review, jobs, CV and Evidence; five stage controls are present, page width does not overflow, and CV headline text remains fully visible. Screenshots were generated in ignored Playwright output. This run's claim is automated layout coverage, not a new visual inspection of every image. |

The ten scenarios are the complete current `frontend/e2e/workflow.spec.ts` suite. Its API
traffic is fulfilled by Playwright fixtures. Fresh output was written below
`frontend/test-results/task7-isolated`; the original failed-run diagnostics remained in
`frontend/test-results`. A credential/response-ID pattern scan of that local output tree found
no matches. No screenshot or historical live artifact was replaced in Git.

## Focused live evaluation status

One `two-job-comparison` run was authorized for the new resume-entry workflow, with intended
output under `docs/evidence/04_System_Tests/live_runs/resume-entry-review`. The initial
boolean-only settings check found no configured credential, so the live step paused with zero
calls at that point. Luke then authorized linking the existing local environment file. After
the ignored worktree symlink was supplied and settings reported a configured credential, the
scenario ran once and exited 0. No secret value was inspected, printed or committed.

The [2026-09-09 live artifact](live_runs/resume-entry-review/2026-09-09-200752573181-two-job-comparison.json)
records `student_profile_01`, `gpt-5.6-luna` and `text-embedding-3-small`. Provider source uses low
reasoning and `store=False`. Five entries were proposed (education, skills, two projects and
experience) and explicitly approved through the synthetic harness; no entry validation issues
were recorded. These are harness approval operations, not evidence of a person reviewing the
live wording.

| Live retrieval rank | Document ID | Score | Selected CV outcome |
| --- | --- | --- | --- |
| 1 | `graduate_ai_engineer` | 0.316572 | Validated; export state recorded. One `interpretive_language` warning about `AI agent prototyping skills`. |
| 2 | `agentic_ai_data_scientist` | 0.313868 | Validated; export state recorded. No validation issues. |
| 3 | `rag_agent_engineer` | 0.309442 | Retrieved only; not selected in this live scenario. |

The artifact records 12 state changes: `collecting_profile` → `profile_confirmed` →
`resume_entries_review` → `resume_entries_approved` → `jobs_retrieved` → `job_selected` →
`cv_draft` → `cv_validated` → `pdf_exported`, then `job_selected` → `cv_draft` → `cv_validated`
→ `pdf_exported` for the second job. The recorded failure is null. The first CV's warning
describes the cited tool-call prototype as supporting the interpretive phrase and invites
review/rewording; it did not block export. No repair or rerun was needed.

The runner records backend export authorization/state; it does not render or save PDF files.
Its safe artifact contains entry wording, entry provenance/trace, retrieval results, state
transitions and CV validation outcomes, but does not preserve the generated CV text or a full
provider transcript. The manifest's `status: planned` is the runner's unchanged setup metadata;
the scenario artifact supplies the actual outcome. Both files passed the credential/response-ID
scan with no matches before inspection and documentation, and the scenario artifact passed its
schema and explicit result assertions. Historical live records were not overwritten.

This establishes one successful live profile/two-job workflow, not five-profile completion
or a reliability estimate. [PR-10](../01_Prompts/prompt_record.md#pr-10---verify-explicit-resume-entry-review-before-job-tailoring)
records the exact executed command, version-pinned prompts, configuration and observed result.

## Evidence boundary

The browser evidence is deterministic and mocked. `frontend/e2e/workflow.spec.ts` intercepts requests to `http://localhost:8000/api/**` and supplies controlled session, resume-entry review, retrieval, CV, validation, export, and provider-failure responses. It establishes UI workflow and responsive-layout behavior against those fixtures; it does not exercise a live backend, call OpenAI, establish live retrieval quality, or evaluate live model output. The separately recorded live scenario above uses real OpenAI responses and synthetic profile input; its scope and artifact limitations are stated explicitly. Historical evidence earlier in this document does not establish additional live completion under the new review workflow.
