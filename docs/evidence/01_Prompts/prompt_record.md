# Prompt Record

This record distinguishes Luke's decisions, coding-agent work, deterministic tests and live model evidence. PR-01 through PR-07 describe earlier development stages; PR-08 records the approved live evaluation on 2026-09-07. PR-10 records the 2026-09-09 resume-entry verification and focused live two-job result, including the initial configuration blocker.

## PR-01 - Choose the frontend

- **Goal:** Select a modern application UI appropriate for a guided CV workflow.
- **Exact prompt:** `Just use react`
- **Proposed change:** Use React, TypeScript and Vite for the staged frontend.
- **Luke's decision:** Approved React rather than a Python-only UI.
- **Verification:** TypeScript checking, component tests, production build and browser review.
- **Actual result:** Frontend quality checks passed and the app rendered without console errors on desktop and narrow mobile viewports.
- **Next improvement:** Maintain browser-level state and responsive-layout assertions as the workflow evolves.

## PR-02 - Remove unnecessary hosted persistence

- **Goal:** Decide whether the assignment needs Supabase.
- **Exact prompt:** `then maybe we dont need supabase`
- **Proposed change:** Keep UUID-keyed sessions in memory because deployment, accounts and persistent storage are not required.
- **Luke's decision:** Approved no Supabase.
- **Verification:** `test_sessions_are_uuid_keyed_and_isolated` creates two sessions and proves that updating one does not change the other.
- **Actual result:** The isolation test passed; the UI states that sessions reset when the API restarts.
- **Next improvement:** Add persistence only if the scope later requires accounts or restart recovery.

## PR-03 - Execute the approved build plan

- **Goal:** Implement the full evidence-backed CV Builder.
- **Exact prompt:** `PLEASE IMPLEMENT THIS PLAN:` followed by the approved ten-stage implementation plan saved in `docs/superpowers/plans/2026-09-05-ai-cv-builder-implementation.md`.
- **Proposed change:** Build the domain workflow, retrieval, bounded agent, provider boundary, CV evidence validation, FastAPI routes, guided React UI, PDF export and evaluation evidence incrementally.
- **Luke's decision:** Approved implementation.
- **Verification:** Red-green tests for each service, linting, type checking, API integration tests, browser tests and visual PDF inspection.
- **Actual result at that stage:** The implementation reached the offline evaluation stage. Live results were subsequently recorded in PR-08 below.
- **Next improvement:** Run the frozen profiles only after the local key exists and Luke explicitly approves live provider calls.

## PR-04 - Keep the provider key local

- **Goal:** Configure OpenAI without exposing a credential to the browser or Git.
- **Exact prompt:** `Then i can paste the key in .env local in this project scope`
- **Proposed change:** Read `OPENAI_API_KEY` from the project-root `.env.local`; keep that file ignored and backend-only.
- **Luke's decision:** Chose manual local entry.
- **Verification:** `.gitignore` excludes `.env.local`; settings load it from the repository root; API error tests assert that validation responses do not reveal the variable.
- **Actual result at that stage:** The key value remained local and was not recorded here. Approved live calls were subsequently made in PR-08 below.
- **Next improvement:** Complete an explicitly approved live smoke test.

## PR-05 - Prompt improvement for profile completeness

- **Goal:** Make follow-up behaviour more specific and aligned with the assessment categories.
- **Before:** `Ask a concise follow-up question when required facts are missing or ambiguous.`
- **Observed weakness:** The prompt did not name the required profile categories, so the model had insufficient guidance about contact details, projects or achievements.
- **Improved prompt:** `Help collect name, contact details, education, skills, experience, projects, achievements, and a target role. Ask one concise, highest-value follow-up question at a time. If the user explicitly says information is unavailable or that they have no item in a category, keep that category absent rather than inventing a placeholder.`
- **Decision:** Keep core confirmation deterministic in Python while improving the model's question-selection guidance.
- **Verification:** `test_agent_prompt_names_profile_categories_without_inventing_unavailable_facts` failed before the change and passed after it.
- **Actual result at that stage:** The provider prompt named the categories and preserved explicit absence. The later live observations and additional repairs are recorded in PR-08 below.
- **Next improvement:** Compare the before/after live responses using the same incomplete introduction.

## PR-06 - Separate relevance from missing requirements

- **Goal:** Meet the brief's requirement to show matched skills and missing requirements separately.
- **Prompt that triggered the check:** The assignment states: `Show matched skills and missing requirements separately`.
- **Proposed change:** Add `matched_skills` and `missing_requirements` to each retrieval result, derive them from confirmed facts and the job's Requirements section, and show them in separate UI panels.
- **Decision:** Treat missing requirements as evidence gaps, not automatic ineligibility.
- **Verification:** A retrieval test and a React accessibility test were written red first, then passed; the full Chrome workflow still passed.
- **Actual result:** API and UI now expose separate evidence categories.
- **Next improvement:** Review live gap quality because token overlap is intentionally conservative.

## PR-07 - Correct the sample-PDF evaluation pattern

- **Goal:** Match the deliverable rule for three sample PDFs.
- **Observed requirement:** Two PDFs must use one confirmed profile for different jobs; the third must use another user.
- **Proposed change:** Reuse Maya's facts for `graduate_ai_engineer` and `agentic_ai_engineer`, then use Liam for `rag_agent_engineer`.
- **Decision:** Replace the earlier three-user sample arrangement.
- **Verification:** The sample test now requires profiles 1 and 2 to match, their target jobs to differ, and profile 3 to be another user.
- **Actual result:** Three one-page A4 PDFs passed fact-reference, text extraction and visual checks.
- **Next improvement:** Replace or supplement these offline reviewed samples with recorded live outputs if the final evaluation demonstrates better evidence.

## PR-08 - Approved live evaluation and observed repairs

- **Approval:** The Task 3 brief recorded user approval to reuse the existing local OpenAI key, send the supplied synthetic data and unseen synthetic profile, and use the frozen expectations. No new exact user quotation is inferred here.
- **Configuration:** `gpt-5.6-luna`, low reasoning; `text-embedding-3-small`; Responses requests keep `store=False` and planner tool calls remain serial. The existing main-checkout environment file was injected into live subprocesses only, without a worktree copy.
- **Initial observations:** Three supplied-profile drafts were blocked for unsupported experience, graduation or headline meaning. A separate isolation draft repeated the experience overstatement. The incomplete agent prioritised name/contact and repeated a name question because the harness did not answer that category. The complete profile passed without an unnecessary follow-up.
- **Repair 1:** Added generation guidance distinguishing listed skills from experience, prohibiting inferred graduation, and requiring backend headline citations to relevant project/experience facts. Added target-role-first agent guidance; corrected factual name replies and made repeated questions fail the scenario. Six deterministic regression cases were observed red, then green.
- **Repair 1 outcome:** Supplied profiles 01/03/05 passed their targeted rerun. Isolation still held, but a fresh draft was blocked for professional identity and team-ownership overstatement. The incomplete agent correctly asked for a role and then name/contact, but the runner rejected an imperative request without a question mark.
- **Repair 2:** Added guidance retaining stated team contributions and avoiding unsupported professional identity; recognised imperative information requests in the runner. Three deterministic regression cases were observed red, then green. The final isolation and incomplete-agent reruns passed their reviewed criteria. The validation prompt and evidence/hash gates were unchanged throughout.
- **Exact prompts and results:** Every [scenario supplement](../06_Live_Evaluation/records/) preserves its actual agent, generation and validation prompt strings, allowlisted tool actions/observations and generated text. This allows the initial, first-repair and second-repair versions to be compared without provider objects.
- **Limits:** Prompt-boundary tests check which instructions are sent; they do not prove semantic reliability. The live reruns are the behavioral observations. Validation outcomes varied across independent generations of the same profile, so one clear run is not a reliability estimate. Retrieval predictions were not revised or tuned to the observed ranking.
- **Full evidence:** [Live evaluation report](../06_Live_Evaluation/2026-09-07-live-run.md), including all failures, reruns, provider-call counts and offline checks.

## PR-09 - Use a reader-facing Harvard-style CV layout

- **Goal:** Make the exported CV look like a conventional Harvard-style résumé and remove internal system labels from the candidate-facing document.
- **Exact prompt:** `Change the layout of the framework, I would love the CV to follow havard style and doesnt contain those words like: Target job evidence: rag_agent_engineer`
- **Constraint:** `Only color for text is black, everything else approve`
- **Proposed change:** Render a black-only, single-column A4 CV with a centred name and headline, confirmed contact facts in the header, conventional section ordering, and no visible target-job IDs or evidence labels. Keep target document IDs in the Evidence stage and assessment records.
- **Luke's decision:** Approved the layout and required all PDF text to remain black.
- **Verification:** Added a content-model test for contact/header/section output and absence of internal labels; added header and footer spacing regressions; regenerated all three sample PDFs; extracted text with `pypdf`; rendered all three pages at 144 DPI for visual inspection; reran frontend contract, Vitest, ESLint, TypeScript, production build and Playwright checks.
- **Actual result:** All three one-page samples use the new layout, contain no `Target job evidence` text or job/profile IDs, and passed visual inspection. The browser suite remained green at 8/8.
- **Next improvement:** Use the same renderer for the final demonstration export and verify the final report package from a fresh extracted copy.

## PR-10 - Verify explicit resume-entry review before job tailoring

- **Scope and approval:** The Task 7 brief authorized final deterministic verification and one focused `two-job-comparison` live evaluation using the existing local credential. This is a task-brief approval record, not a reconstructed quotation from Luke.
- **Implementation under test:** `af34678` (`test: cover reviewed resume entry workflow`), including the preceding reviewed resume-entry changes. Profile facts and proposed resume wording are separate; the student reviews, saves and explicitly approves entries before job retrieval. CV generation receives confirmed contact facts and approved entries, while each selected job remains targeting context.
- **Exact executed live command:** `PYTHONPATH=backend .venv/bin/python scripts/run_live_evaluation.py --scenario two-job-comparison --output-dir docs/evidence/04_System_Tests/live_runs/resume-entry-review`. The import path allows the root-level runner to load the local backend package; it does not alter scenario inputs or models.
- **Exact prompt source:** The unchanged source strings at `af34678` and the live execution commit `1b61d5a` are `RESUME_ENTRY_PROPOSAL_INSTRUCTIONS`, `RESUME_ENTRY_VALIDATION_INSTRUCTIONS`, `CV_GENERATION_INSTRUCTIONS` and `CV_VALIDATION_INSTRUCTIONS` in `backend/app/providers/openai_provider.py`. The proposal instruction begins `Turn confirmed_facts into concise resume entries for` and ends `Return proposed entries only; the student must explicitly approve them.` The audit instruction begins `Audit every visible item in entries_to_audit against` and ends `Use the exact entry_id for every issue. No external knowledge is candidate evidence.` These version-pinned constants supply the complete instructions used by the runner; the excerpts identify them. The safe scenario artifact does not contain a full provider request/response transcript or generated CV text.
- **Live configuration:** Runner-selected `gpt-5.6-luna` and `text-embedding-3-small`, also recorded in the artifact. Structured Responses generation/audit requests use low reasoning and `store=False`; proposal/CV generation allow 3000 output tokens and entry/CV audits allow 1800. The imported synthetic input was `student_profile_01`; the runner selected the first two live retrieval results.
- **Fresh deterministic results (2026-09-09 AEST):** Started with a clean working tree. Backend: 205 tests passed in 1.99 seconds, Ruff passed, and mypy passed across 17 source files. Frontend: generated contract matched; 28 tests across three files passed; lint, typecheck and production build passed. All ten mocked browser tests passed in 38.3 seconds with an isolated worktree server on port 5197.
- **Observed browser environment issue:** The initial default `npm run e2e` reused the main checkout's port-5173 server and displayed the previous four-stage UI. Two tests timed out waiting for `Create resume entries`; the third was interrupted and seven did not run. That process was left untouched. The full suite then passed with a temporary configuration using port 5197, `--strictPort` and `reuseExistingServer: false`. The temporary configuration was removed after verification; no product repair was needed.
- **Initial configuration blocker and resolution:** The initial boolean-only settings check found no configured credential, so no provider call was made then. Luke subsequently authorized linking the existing local environment file. With an ignored worktree `.env.local` symlink in place, settings reported a configured credential. Its value was never printed, inspected or committed. The focused scenario then ran once and exited 0; no repair or rerun was needed.
- **Actual live outcome:** The [real scenario artifact](../04_System_Tests/live_runs/resume-entry-review/2026-09-09-200752573181-two-job-comparison.json) records five proposed entries: education, skills, two projects and one experience entry. The synthetic harness explicitly invoked the approval service for each; all five became approved with no entry validation issues. Retrieval ranked `graduate_ai_engineer` (0.316572), `agentic_ai_data_scientist` (0.313868), and `rag_agent_engineer` (0.309442). The first two were selected sequentially; both reached `cv_validated` and `pdf_exported`, with `failure: null`.
- **Observed CV audit:** The `graduate_ai_engineer` CV received one `interpretive_language` warning for `AI agent prototyping skills`, described by the audit as a reasonable interpretation of the cited tool-call prototype. The `agentic_ai_data_scientist` CV had no validation issues. Both passed the backend export gate. The runner recorded export state; it did not render or save actual PDFs, and its approval events represent synthetic harness actions, not a human review session.
- **Artifact review and limits:** The live artifact and manifest passed the credential/response-ID scan with no matches, then the artifact passed schema validation and explicit outcome assertions. The manifest retains the runner's initial `status: planned`; the linked scenario artifact is the result record. Fresh Playwright outputs also scanned without matches. One profile/two jobs is not five-profile completion or a semantic reliability estimate. Earlier PR-08 live artifacts remain historical evidence for the earlier workflow.
