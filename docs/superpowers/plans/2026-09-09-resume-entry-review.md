# Resume Entry Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert confirmed student facts into explicit, reviewable, evidence-linked resume entries before those entries are used to retrieve jobs or generate a tailored CV.

**Architecture:** Keep `Fact` as the evidence authority and add a derived `ResumeEntry` layer to `Session`. A dedicated backend service proposes, validates, edits, removes, and approves entries; only approved substantive entries and confirmed contact facts reach CV generation. React adds a Resume entries review stage between Profile and Job matches, while the Evidence stage retains the complete audit trail.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, OpenAI Responses API, pytest, Ruff, mypy, React 19, TypeScript, Vite, Vitest, React Testing Library, Playwright, and `@react-pdf/renderer`.

**Spec:** `docs/superpowers/specs/2026-09-09-resume-entry-review-design.md`

## Global Constraints

- Original student facts remain the only evidence authority; proposed resume entries never modify them.
- Every reader-visible entry field and bullet must cite one or more confirmed source facts.
- Professional wording may clarify and structure facts, but may not invent dates, employers, titles, seniority, metrics, outcomes, ownership, qualifications, work rights, or eligibility.
- Listed skills are not evidence of work experience; job requirements never become candidate facts.
- Students explicitly approve entries before those entries can reach retrieval or CV generation.
- The main profile/CV/PDF UI must not expose internal fact or job identifiers; the Evidence stage must expose audit mappings.
- Keep the existing sequential two-job workflow; do not build a multi-CV archive or comparison UI.
- Do not store provider responses (`store=False`), do not expose API keys, and do not change supplied job data.

## File structure

| File | Responsibility |
| --- | --- |
| `backend/app/domain/models.py` | Pydantic entry models, entry states, workflow states, and session fields. |
| `backend/app/domain/workflow.py` | State transitions, downstream invalidation, and state-derived entry eligibility. |
| `backend/app/services/resume_entries.py` | Entry proposal orchestration plus deterministic provenance checks and approval rules. |
| `backend/app/services/cv.py` | Restrict CV-generation input to approved entries plus contact facts. |
| `backend/app/providers/base.py` | Provider contracts for entry proposal/validation and restricted CV input. |
| `backend/app/providers/openai_provider.py` | Strict structured Responses calls and instructions for proposal/entry validation. |
| `backend/app/providers/fake.py`, `backend/app/providers/unavailable.py` | Deterministic offline test behavior and recoverable unavailable-provider behavior. |
| `backend/app/main.py` | Resume-entry endpoints, service wiring, and consistent error responses. |
| `backend/tests/test_resume_entries.py` | Isolated provenance, approval, invalidation, and provider-boundary tests. |
| `backend/tests/test_api.py`, `test_cv_service.py`, `test_live_evaluation_artifacts.py` | API, CV gating, two-job workflow, and live-runner regression coverage. |
| `scripts/run_live_evaluation.py` | Insert deterministic entry proposal/approval into live evaluation workflows. |
| `frontend/src/components/ResumeEntryStage.tsx` | Reader-facing entry review/edit/remove/approve UI. |
| `frontend/src/components/StageNav.tsx`, `App.tsx`, `api.ts`, `types.ts`, `styles.css` | Five-stage navigation, API calls, generated-contract bindings, integration, and responsive styling. |
| `frontend/src/components/EvidenceStage.tsx` | Resume-entry-to-fact audit map and trace rendering. |
| `frontend/src/App.test.tsx`, `frontend/e2e/workflow.spec.ts` | Unit and browser tests for gating, editing, invalidation, desktop, and mobile. |
| `frontend/openapi.json`, `frontend/src/generated/api-schema.ts` | Regenerated FastAPI contract artefacts. |
| `docs/evidence/01_Prompts/prompt_record.md`, `docs/evidence/04_System_Tests/acceptance_coverage.md` | Authentic implementation and verification evidence after tests are run. |

---

### Task 1: Define resume-entry data and transition invariants

**Files:**
- Modify: `backend/app/domain/models.py`
- Modify: `backend/app/domain/workflow.py`
- Create: `backend/tests/test_resume_entries.py`
- Modify: `backend/tests/test_session_workflow.py`

**Interfaces:**
- Produces `ResumeEntryKind`, `ResumeEntryStatus`, `ResumeText`, `ResumeEntryDetail`, `ResumeEntry`, `ResumeEntryEdit`, `ResumeEntryValidationIssue`, and `Session.resume_entries` / `Session.resume_entries_revision`.
- Produces workflow methods `set_resume_entries(session_id, entries)`, `update_resume_entry(session_id, entry_id, edit)`, `approve_resume_entry(session_id, entry_id, issues)`, `delete_resume_entry(session_id, entry_id)`, and `approved_resume_entries(session)`.
- Later tasks consume `SessionState.RESUME_ENTRIES_REVIEW` and `SessionState.RESUME_ENTRIES_APPROVED`.

- [ ] **Step 1: Write failing model and workflow tests**

```python
def test_resume_entry_requires_per_item_confirmed_fact_provenance() -> None:
    entry = ResumeEntry(
        kind=ResumeEntryKind.EXPERIENCE,
        heading=ResumeText(text="Data Science Intern", fact_ids=["fact-experience"]),
        bullets=[ResumeText(text="Investigated AI-chatbot failures.", fact_ids=["fact-experience"])],
        source_fact_ids=["fact-experience"],
    )
    assert entry.status is ResumeEntryStatus.PROPOSED


def test_profile_revision_marks_linked_entry_for_review_and_clears_cv() -> None:
    # Start with approved entry, jobs, selected job, validated CV; edit its source fact.
    revised = workflow.update_profile(session_id, [FactInput(field="project", value="New work")], source_reference="message-2")
    assert revised.resume_entries[0].status is ResumeEntryStatus.NEEDS_REVIEW
    assert revised.retrieval_results == []
    assert revised.cv is None
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_resume_entries.py tests/test_session_workflow.py -q`

Expected: import or attribute failures for the new models and workflow methods.

- [ ] **Step 3: Add strict models and states**

In `models.py`, add the states in workflow order and use structured text rather than a loose map:

```python
class ResumeEntryStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"


class ResumeText(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    fact_ids: list[str] = Field(min_length=1)


class ResumeEntry(StrictModel):
    entry_id: str = Field(default_factory=lambda: f"resume-entry-{uuid4()}")
    kind: ResumeEntryKind
    heading: ResumeText
    organisation_or_context: ResumeText | None = None
    details: list[ResumeEntryDetail] = Field(default_factory=list)
    bullets: list[ResumeText] = Field(default_factory=list, max_length=3)
    source_fact_ids: list[str] = Field(min_length=1)
    status: ResumeEntryStatus = ResumeEntryStatus.PROPOSED
```

Validate non-blank display text and require `source_fact_ids` to equal the de-duplicated union of every nested `fact_ids`. Add session fields with empty defaults so older fixtures remain valid.

- [ ] **Step 4: Implement workflow rules**

In `workflow.py`:

```python
def approved_resume_entries(self, session: Session) -> list[ResumeEntry]:
    return [entry for entry in session.resume_entries if entry.status is ResumeEntryStatus.APPROVED]

def _reconcile_resume_state(self, session: Session) -> None:
    has_approved_substantive_entry = any(
        entry.status is ResumeEntryStatus.APPROVED
        and entry.kind in {ResumeEntryKind.EXPERIENCE, ResumeEntryKind.PROJECT,
                           ResumeEntryKind.EDUCATION, ResumeEntryKind.ACHIEVEMENT}
        for entry in session.resume_entries
    )
    session.state = (
        SessionState.RESUME_ENTRIES_APPROVED
        if has_approved_substantive_entry
        else SessionState.RESUME_ENTRIES_REVIEW
    )
```

`set_resume_entries` is allowed only from `PROFILE_CONFIRMED`, review, approved, or downstream states; it replaces old entries with `proposed` entries, clears downstream results, and records `resume_entries_proposed`. Editing retains immutable fact IDs, switches the entry to `needs_review`, clears downstream results, and records `resume_entry_updated`. Approval only changes `proposed`/`needs_review` to `approved`, reconciles state, and records `resume_entry_approved`. Deletion removes only the derived entry, reconciles state, and records `resume_entry_removed`.

Extend `update_profile` to calculate changed fact IDs before mutation, mark linked entries `needs_review`, increment the entry revision when any status changes, and still clear all jobs/CVs/export state. Do not delete raw facts when an entry is removed.

Restrict `set_retrieval_results` to `RESUME_ENTRIES_APPROVED` and downstream states. Preserve current behavior when job selection replaces the active CV.

- [ ] **Step 5: Run focused tests and static checks**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_resume_entries.py tests/test_session_workflow.py -q
../.venv/bin/python -m ruff check app tests
../.venv/bin/python -m mypy app
```

Expected: all pass.

- [ ] **Step 6: Commit the invariant layer**

```bash
git add backend/app/domain/models.py backend/app/domain/workflow.py \
  backend/tests/test_resume_entries.py backend/tests/test_session_workflow.py
git commit -m "feat: add reviewed resume entry workflow"
```

### Task 2: Build the provider and resume-entry service boundary

**Files:**
- Create: `backend/app/services/resume_entries.py`
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/fake.py`
- Modify: `backend/app/providers/unavailable.py`
- Modify: `backend/app/providers/openai_provider.py`
- Modify: `backend/app/services/cv.py`
- Modify: `backend/tests/test_resume_entries.py`
- Modify: `backend/tests/test_openai_provider.py`
- Modify: `backend/tests/test_cv_service.py`

**Interfaces:**
- Consumes Task 1’s `ResumeEntry` models and workflow methods.
- Produces `ResumeEntryService.propose`, `.edit`, `.approve`, and `.delete`.
- Extends `CVProvider` with `propose_resume_entries(confirmed_facts)`, `validate_resume_entries(entries, confirmed_facts)`, and `generate_cv(contact_facts, approved_entries, job)`.

- [ ] **Step 1: Write failing service and provider tests**

```python
def test_approval_rejects_unknown_or_unconfirmed_entry_evidence() -> None:
    entry = proposed_entry(fact_ids=["fact-not-in-session"])
    workflow.set_resume_entries(session_id, [entry])
    with pytest.raises(ResumeEntryEvidenceError, match="confirmed profile fact"):
        service.approve(session_id, entry.entry_id)


def test_cv_provider_receives_only_contact_facts_and_approved_entries() -> None:
    service.generate(session_id, job)
    assert fake_provider.cv_contact_fields == {"name", "email"}
    assert fake_provider.cv_entry_ids == [approved_entry.entry_id]


def test_openai_entry_proposal_is_structured_private_and_non_embellishing() -> None:
    provider.propose_resume_entries([confirmed_experience_fact])
    assert captured.kwargs["store"] is False
    assert captured.kwargs["text_format"] is ResumeEntryProposal
    assert "metrics" in captured.kwargs["instructions"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_resume_entries.py tests/test_openai_provider.py tests/test_cv_service.py -q`

Expected: absent service methods and incompatible provider signatures.

- [ ] **Step 3: Implement deterministic service checks**

Create `ResumeEntryService` with a private `_entry_issues(session, entry)` that checks every nested citation, every `source_fact_ids` value, and the exact source-ID union against confirmed facts in that session. Reject malformed/foreign/draft/deleted evidence with `ResumeEntryEvidenceError` before state mutation.

```python
def approve(self, session_id: str, entry_id: str) -> Session:
    session = self._workflow.get_session(session_id)
    entry = self._entry(session, entry_id)
    if issues := self._entry_issues(session, entry):
        raise ResumeEntryEvidenceError(issues[0].message)
    semantic_issues = self._provider.validate_resume_entries(
        [entry], self._confirmed_facts(session)
    )
    if any(issue.severity is ValidationSeverity.ERROR for issue in semantic_issues):
        raise ResumeEntryEvidenceError("This resume entry adds information not confirmed in your profile.")
    return self._workflow.approve_resume_entry(session_id, entry_id, semantic_issues)
```

Keep warnings in `session.resume_entry_validation_issues`; user approval is the explicit review action that accepts a non-blocking warning. `propose` must require a confirmed profile, call the provider with confirmed facts only, run deterministic validation over every returned entry, then set entries atomically. An unavailable/malformed provider response must leave the session unchanged.

- [ ] **Step 4: Make provider inputs deliberately narrow**

In `base.py`, replace the broad CV generation input with:

```python
def generate_cv(
    self,
    contact_facts: list[Fact],
    approved_entries: list[ResumeEntry],
    job: Job,
) -> CVDocument: ...
```

Add `ResumeEntryProvider` protocol methods. Adapt fake/unavailable providers and every test double to implement the new methods.

In `CVService.generate`, obtain `workflow.approved_resume_entries(session)` and reject empty substantive sets. Pass only confirmed contact facts (`name`, `email`, `phone`, `github`, `linkedin`) and approved entries to the provider; keep the existing claim-to-raw-fact validation for the generated CV.

- [ ] **Step 5: Implement strict OpenAI calls and prompts**

Use `responses.parse` with `store=False`, low reasoning effort, and Pydantic response schemas:

```python
response = self._client.responses.parse(
    model=self._model,
    instructions=RESUME_ENTRY_PROPOSAL_INSTRUCTIONS,
    input=json.dumps({"confirmed_facts": [fact.model_dump(mode="json") for fact in facts]}),
    text_format=ResumeEntryProposal,
    store=False,
    reasoning={"effort": "low"},
    max_output_tokens=3000,
)
```

The proposal prompt must explicitly require one-to-three concise bullets; cite each visible item; preserve group context; treat skills as skills; and return no field rather than infer an employer, title, date, metric, outcome, ownership, seniority, or qualification. The entry-validation prompt audits only cited confirmed facts and uses errors for fabricated substance, warnings only for modest evidence-grounded interpretation.

Update CV-generation input/prompt to include `confirmed_contact_facts` and `approved_resume_entries`, never `ProfileDraft` wholesale. Preserve existing headline and claim citation requirements.

- [ ] **Step 6: Run focused tests and static checks**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_resume_entries.py tests/test_openai_provider.py tests/test_cv_service.py -q
../.venv/bin/python -m ruff check app tests
../.venv/bin/python -m mypy app
```

Expected: all pass, including two distinct job-targeted CVs created from one unchanged approved-entry set.

- [ ] **Step 7: Commit provider and service work**

```bash
git add backend/app/services/resume_entries.py backend/app/services/cv.py \
  backend/app/providers backend/tests/test_resume_entries.py \
  backend/tests/test_openai_provider.py backend/tests/test_cv_service.py
git commit -m "feat: generate and validate reviewed resume entries"
```

### Task 3: Expose the guarded resume-entry API and update the contract

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/generated/api-schema.ts`

**Interfaces:**
- Consumes `ResumeEntryService` from Task 2.
- Produces:
  - `POST /api/sessions/{session_id}/resume-entries/propose`
  - `PUT /api/sessions/{session_id}/resume-entries/{entry_id}`
  - `POST /api/sessions/{session_id}/resume-entries/{entry_id}/approve`
  - `DELETE /api/sessions/{session_id}/resume-entries/{entry_id}`

- [ ] **Step 1: Write failing API tests for complete flow and forbidden actions**

```python
def test_api_requires_approved_resume_entry_before_retrieval() -> None:
    client.post(f"{base}/profile/confirm")
    assert client.post(f"{base}/jobs/retrieve").status_code == 409
    proposed = client.post(f"{base}/resume-entries/propose")
    entry_id = proposed.json()["resume_entries"][0]["entry_id"]
    assert client.post(f"{base}/resume-entries/{entry_id}/approve").status_code == 200
    assert client.post(f"{base}/jobs/retrieve").status_code == 200


def test_api_cannot_edit_provenance_or_approve_foreign_entry() -> None:
    assert client.put(f"{base}/resume-entries/{foreign_id}", json=edit_payload).status_code == 409
```

- [ ] **Step 2: Run API tests to verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_api.py -q`

Expected: 404 responses for resume-entry endpoints and old workflow assumptions failing.

- [ ] **Step 3: Wire service and typed request models**

Add `resume_entries: ResumeEntryService` to `ApplicationServices`. Use the Task 1 `ResumeEntryEdit` request model to permit display-text edits only and reuse server-owned citation lists by index; reject altered labels/counts/citations so the browser never assigns evidence. Extend CORS methods with `DELETE`.

Routes return the updated `Session`, use current error-envelope handlers, and surface deterministic evidence errors as `422` with `resume_entry_evidence_error`. State conflicts and unknown entry IDs must remain `409` and `404` respectively. Do not add entry proposal to `AGENT_TOOLS`: explicit user action is the review boundary.

- [ ] **Step 4: Regenerate and check the frontend API contract**

Run:

```bash
cd frontend
npm run contract:generate
npm run contract:check
```

Expected: `openapi.json` and `src/generated/api-schema.ts` exactly match the FastAPI app, including all resume-entry types and routes.

- [ ] **Step 5: Run backend tests, lint, and typing**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_api.py tests/test_resume_entries.py tests/test_cv_service.py -q
../.venv/bin/python -m ruff check app tests
../.venv/bin/python -m mypy app
```

Expected: all pass.

- [ ] **Step 6: Commit API and contract**

```bash
git add backend/app/main.py backend/tests/test_api.py frontend/openapi.json \
  frontend/src/generated/api-schema.ts
git commit -m "feat: expose reviewed resume entry api"
```

### Task 4: Add the guided Resume entries stage to React

**Files:**
- Create: `frontend/src/components/ResumeEntryStage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/StageNav.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes generated `ResumeEntry`, `ResumeEntryEdit`, and expanded `Session` types from Task 3.
- Produces `ResumeEntryStage` with `onPropose`, `onEdit`, `onApprove`, and `onDelete` callbacks.

- [ ] **Step 1: Write failing React tests**

```tsx
it('locks job matches until a substantive resume entry is approved', () => {
  render(<WorkflowApp session={resumeReviewSession} {...props} />)
  expect(screen.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Approve entry' }))
  expect(onApproveResumeEntry).toHaveBeenCalledWith('resume-entry-1')
})

it('shows polished content beside human-readable source wording without fact ids', () => {
  render(<ResumeEntryStage session={resumeReviewSession} {...props} />)
  expect(screen.getByText('Based on what you told us')).toBeVisible()
  expect(screen.getByText('Built a Python course-planning API.')).toBeVisible()
  expect(screen.queryByText('fact-project')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the unit tests to verify they fail**

Run: `cd frontend && npm test -- --run src/App.test.tsx`

Expected: missing stage, props, and generated types.

- [ ] **Step 3: Add API client and application callbacks**

Add typed `api.proposeResumeEntries`, `api.updateResumeEntry`, `api.approveResumeEntry`, and `api.deleteResumeEntry` methods. Pass them through `WorkflowApp` and use the existing `run` helper so the session is always refreshed after a recoverable API error.

Extend `Stage` to `profile | resume | jobs | cv | evidence`. `preferredStage` should choose Resume entries for either resume state, Job matches for retrieved jobs, and CV studio after job selection. Job matches must require `resume_entries_approved`, not merely `profile_confirmed`.

- [ ] **Step 4: Implement the review component**

Render an action card when there are no entries:

```tsx
<h3>Turn your confirmed facts into CV-ready entries</h3>
<p>We will structure what you told us. Review every entry before it can appear in your CV.</p>
<button onClick={onPropose}>Create resume entries</button>
```

For every entry, render a conventional preview, a status pill, editable heading/context/detail/bullet text, a `Based on what you told us` list resolved through `session.profile.facts`, and `Save changes`, `Approve entry`, and `Remove entry` controls. Do not render fact IDs, source message IDs, or job IDs in this stage. Disable actions while busy and state clear recovery copy for `needs_review`.

- [ ] **Step 5: Style and protect mobile layout**

Add focused `.resume-entry-grid`, `.resume-entry-card`, `.entry-source-list`, `.entry-status`, and `.entry-actions` styles following the existing restrained black/white/slate system. At 375 px, cards must stack, text controls remain legible, and action buttons must not force horizontal overflow. Do not alter the approved black-text PDF palette.

- [ ] **Step 6: Run frontend tests, lint, typecheck, and build**

Run:

```bash
cd frontend
npm run contract:check
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all pass.

- [ ] **Step 7: Commit the review UI**

```bash
git add frontend/src/components/ResumeEntryStage.tsx frontend/src/App.tsx \
  frontend/src/components/StageNav.tsx frontend/src/api.ts frontend/src/types.ts \
  frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: add resume entry review stage"
```

### Task 5: Extend audit, CV, and live-evaluation workflows

**Files:**
- Modify: `frontend/src/components/EvidenceStage.tsx`
- Modify: `frontend/src/components/CVStage.tsx`
- Modify: `backend/tests/test_cv_service.py`
- Modify: `backend/app/services/live_evaluation.py`
- Modify: `scripts/run_live_evaluation.py`
- Modify: `backend/tests/test_live_evaluation_artifacts.py`

**Interfaces:**
- Consumes approved-entry session state and Task 2’s CV provider contract.
- Produces entry-to-fact audit records and live scenarios that reach export only after proposal and approval.

- [ ] **Step 1: Write failing regression tests**

```python
def test_two_jobs_use_the_same_approved_entry_set_but_produce_distinct_cvs() -> None:
    first = generate_for("job-1")
    second = generate_for("job-2")
    assert provider.entry_ids_for_calls == [["resume-entry-project"], ["resume-entry-project"]]
    assert first.target_job_id != second.target_job_id


def test_live_unseen_scenario_records_resume_review_before_retrieval(tmp_path: Path) -> None:
    result = main(["--scenario", "unseen", "--output-dir", str(tmp_path)], services_factory=offline_services)
    assert "resume_entries_approved" in transition_targets(tmp_path)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_cv_service.py tests/test_live_evaluation_artifacts.py -q`

Expected: outdated provider signature/live transitions fail.

- [ ] **Step 3: Make the CV and Evidence views explain the new layer**

In `CVStage`, change the pre-generation explanation to say that tailoring uses approved resume entries and confirmed contact information. Preserve existing claim-level evidence support, semantic validation, content-hash locking, and PDF behavior.

In `EvidenceStage`, add a `Resume entry map` card between Profile facts and CV claim map. It may show raw entry IDs/fact IDs because this is the audit screen, and must show entry status, reader-facing text, source facts, entry validation warnings, and proposal/edit/approval trace events.

- [ ] **Step 4: Update evaluation runner and its offline provider**

After `_import_profile`, invoke the new service to propose deterministic entries, approve all valid substantive entries for an automated evaluation run, and record both transitions before retrieval. Adapt `OfflineEvaluationProvider` and leakage test doubles to the narrowed provider protocol. Keep source-isolation checks and key/response-ID redaction unchanged.

- [ ] **Step 5: Run focused and full backend verification**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_cv_service.py tests/test_live_evaluation_artifacts.py -q
../.venv/bin/python -m pytest
../.venv/bin/python -m ruff check app tests
../.venv/bin/python -m mypy app
```

Expected: all pass.

- [ ] **Step 6: Commit audit and evaluation integration**

```bash
git add frontend/src/components/EvidenceStage.tsx frontend/src/components/CVStage.tsx \
  backend/app/services/live_evaluation.py scripts/run_live_evaluation.py \
  backend/tests/test_cv_service.py backend/tests/test_live_evaluation_artifacts.py
git commit -m "feat: trace approved resume entries through cv evaluation"
```

### Task 6: Complete browser coverage and responsive verification

**Files:**
- Modify: `frontend/e2e/workflow.spec.ts`
- Modify: `frontend/src/App.test.tsx` if a stable UI regression needs unit coverage

**Interfaces:**
- Consumes the full mocked resume-entry API contract from Tasks 3–5.
- Produces browser proof for review gating, edits, invalidation, failure recovery, isolation, sequential two-job use, and desktop/mobile layout.

- [ ] **Step 1: Update the Playwright mock session and routes**

Add `resume_entries: []`, `resume_entries_revision: 0`, and `resume_entry_validation_issues: []` to every fixture. Mock proposal, edit, approval, and deletion routes with the same session mutation semantics as the backend. Change `reachValidatedCV` to confirm profile, create entries, approve an entry, retrieve, select, generate, and validate.

- [ ] **Step 2: Write browser assertions before updating implementation fixtures**

```ts
test('requires an approved entry and re-locks jobs after a source-fact revision', async ({ page }) => {
  await page.getByRole('button', { name: 'Create resume entries' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeEnabled()
  // revise profile; linked entry becomes Needs review and the download control disappears
})

test('review cards remain usable at desktop and phone widths', async ({ page }) => {
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})
```

- [ ] **Step 3: Run Playwright to verify failures, then complete route fixture updates**

Run: `cd frontend && npm run e2e`

Expected before mock updates: old workflow selectors cannot reach Job matches. Expected after updates: all existing tests plus new review-specific cases pass.

- [ ] **Step 4: Cover key assessment cases in the browser**

Assert all of the following:

- Job matches and CV studio are disabled before substantive entry approval.
- A student sees original source wording, edits entry text, saves it, then approves it.
- A source fact revision marks its entry Needs review, clears job/CV state, and blocks PDF export.
- A provider failure after a committed profile edit preserves the changed source facts and shows recovery copy.
- Two browser contexts remain visually/session isolated.
- One approved profile can select job A and then job B sequentially; active CV target changes and old PDF is unavailable.
- The review stage, job stage, CV stage, and Evidence stage have no horizontal overflow at 1440 px and 375 px.

- [ ] **Step 5: Run the frontend quality gate**

Run:

```bash
cd frontend
npm run contract:check
npm test -- --run
npm run lint
npm run typecheck
npm run build
npm run e2e
```

Expected: all pass.

- [ ] **Step 6: Commit browser coverage**

```bash
git add frontend/e2e/workflow.spec.ts frontend/src/App.test.tsx
git commit -m "test: cover reviewed resume entry workflow"
```

### Task 7: Run final verification and record real evidence

**Files:**
- Modify: `docs/evidence/01_Prompts/prompt_record.md`
- Modify: `docs/evidence/04_System_Tests/acceptance_coverage.md`
- Modify only if live results require a genuine repair: focused code/test files from the failed check

**Interfaces:**
- Consumes all completed functionality and the existing live evaluation runner.
- Produces factual, redacted assessment evidence; no invented results.

- [ ] **Step 1: Run all deterministic gates from a clean working tree**

Run:

```bash
git status --short
cd backend && ../.venv/bin/python -m pytest && ../.venv/bin/python -m ruff check app tests && ../.venv/bin/python -m mypy app
cd ../frontend && npm run contract:check && npm test -- --run && npm run lint && npm run typecheck && npm run build && npm run e2e
```

Expected: no unexpected working-tree changes and every command exits 0.

- [ ] **Step 2: Run a focused live-provider scenario only after deterministic success**

Run with the local `.env.local` key present but never print it:

```bash
.venv/bin/python scripts/run_live_evaluation.py \
  --scenario two-job-comparison \
  --output-dir docs/evidence/04_System_Tests/live_runs/resume-entry-review
```

Record actual model/configuration, transitions, selected document IDs, entry proposal/approval outcome, CV validation results, and any repair. Do not overwrite existing evidence with a fabricated successful run.

- [ ] **Step 3: Review the recorded artefact for accidental secrets and evidence truthfulness**

Run:

```bash
rg -n -i "sk-[a-z0-9]|api[_ -]?key|resp_[a-z0-9]|chatcmpl-|cmpl-" \
  docs/evidence/04_System_Tests/live_runs/resume-entry-review || true
```

Expected: no credentials or provider response IDs. If a live run fails, record the failure as-is, repair the real defect with a new failing regression test, rerun only the affected scenario, and retain both records.

- [ ] **Step 4: Update evidence documents with observed facts only**

Add an exact prompt/configuration record and test outcome to `prompt_record.md`. Update coverage to show the new review stage, provenance gate, profile-revision invalidation, two-job behavior, browser/mobile checks, and the actual live scenario result. Do not claim five-profile completion unless all five runs were newly completed under this new workflow.

- [ ] **Step 5: Commit verified evidence**

```bash
git add docs/evidence/01_Prompts/prompt_record.md \
  docs/evidence/04_System_Tests/acceptance_coverage.md \
  docs/evidence/04_System_Tests/live_runs/resume-entry-review
git commit -m "test: record resume entry review verification"
```

## Final cross-check

- Task 1 implements the separate data layer, state machine, and invalidation rules.
- Task 2 enforces deterministic provenance plus structured, non-embellishing model behavior and restricts CV input.
- Task 3 exposes typed guarded endpoints and regenerates the frontend contract.
- Task 4 implements the student-facing review flow and responsive UI.
- Task 5 preserves job-specific CV tailoring, sequential two-job behavior, Evidence audit, and evaluation support.
- Task 6 proves browser gating, revisions, provider recovery, isolation, PDF locking, and desktop/mobile behavior.
- Task 7 records only real, redacted verification evidence.
