# Live OpenAI Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce honest, reproducible live-model evidence for the CV Builder without exposing the local API key or changing predictions after results are seen.

**Architecture:** A backend-side evaluation runner will turn supplied synthetic assessment records into confirmed facts, then exercise the real embedding, generation, validation, and export-state services. Separate agent scenarios will measure follow-up quality. It will emit redacted JSON evidence; Markdown records will be written only from those artifacts.

**Tech Stack:** Python 3.12, FastAPI services, OpenAI Responses API, `gpt-5.6-luna`, `text-embedding-3-small`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-ai-cv-builder-design.md`

## Global Constraints

- Reuse the ignored project-root `.env.local` key; never print, commit, or copy it.
- Send only supplied synthetic assessment data and the synthetic unseen profile; retain `store=False`.
- Freeze predictions before the first profile retrieval. Preserve disagreements and failures.
- Record prompts, model IDs, document IDs, state transitions, actions, observations, validation issues, and repair/rerun evidence.
- Keep live calls out of pytest. A user-approved runner performs all external calls.
- Never mark a PDF exported unless the existing validation/hash gate actually permits it.

---

### Task 1: Freeze predictions and define safe artifacts

**Files:**
- Modify: `docs/evidence/03_Retrieval/retrieval_results.md`
- Create: `backend/app/services/live_evaluation.py`
- Create: `backend/tests/test_live_evaluation_artifacts.py`

**Interfaces:**
- Produces: `LiveRunRecord` containing safe model configuration, profile ID, messages, retrieval results, transitions, CV results, and a failure field.

- [ ] **Step 1: Freeze the reviewed predictions**

Replace each `Pending` in the six-row prediction table with `Approved before live retrieval on 2026-09-07`. Do not add any observed result.

- [ ] **Step 2: Write the failing safety test**

```python
def test_live_run_record_rejects_key_like_text() -> None:
    with pytest.raises(ValidationError):
        LiveRunRecord(run_id="run-1", profile_id="student_profile_01", note="sk-proj-not-allowed")
```

- [ ] **Step 3: Verify RED**

Run `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_live_evaluation_artifacts.py -q` and confirm it fails because `LiveRunRecord` is missing.

- [ ] **Step 4: Implement minimal artifact types**

Create Pydantic record types and a recursive `sk-` prefix rejection guard. Do not persist keys, raw provider objects, or response IDs.

- [ ] **Step 5: Verify GREEN and commit**

Run the focused test again, then commit the evidence freeze and artifact contract.

### Task 2: Build an offline-tested runner

**Files:**
- Create: `scripts/run_live_evaluation.py`
- Modify: `backend/app/services/live_evaluation.py`
- Modify: `backend/tests/test_live_evaluation_artifacts.py`

**Interfaces:**
- Consumes: `ApplicationServices`, supplied JSON records, and `--output-dir`.
- Produces: one artifact per scenario and a manifest created before provider calls.

- [ ] **Step 1: Write failing helper tests**

```python
def test_profile_to_confirmed_facts_excludes_name() -> None:
    facts = profile_to_confirmed_facts({"name": "Synthetic Name", "degree": "Bachelor", "target_roles": ["AI Intern"]}, "student_profile_01")
    assert [fact.field for fact in facts] == ["education", "target_role"]

def test_export_outcome_records_a_blocked_draft() -> None:
    assert export_outcome(SessionState.CV_DRAFT) == "blocked"
```

- [ ] **Step 2: Verify RED**

Run the focused test and confirm it fails because the helpers are missing.

- [ ] **Step 3: Implement minimal conversion and recorder**

Use imported-test-profile sources for deterministic education, skills, projects, experience, and singular target-role facts. Record top-three IDs/scores/excerpts, state transitions, selected job, validation issues, and an `exported` or `blocked` result.

- [ ] **Step 4: Implement explicit scenario flags**

```text
--scenario supplied-five
--scenario two-job-comparison
--scenario session-isolation
--scenario complete-agent
--scenario incomplete-agent
--scenario unseen
```

The incomplete-agent scenario must retain actual questions and factual replies. The complete-agent scenario must preserve the full supplied message and flag a question as a failure for review.

- [ ] **Step 5: Verify offline checks and commit**

Run focused pytest, Ruff, and mypy. Commit the runner only after all three pass without a provider call.

### Task 3: Run and document the approved live evaluation

**Files:**
- Create: `docs/evidence/06_Live_Evaluation/2026-09-07-live-run.md`
- Create: `docs/evidence/06_Live_Evaluation/records/` from secret-scanned runner output
- Modify: `docs/evidence/04_System_Tests/five_profile_results.md`
- Modify: `docs/evidence/04_System_Tests/two_job_comparison.md`
- Modify: `docs/evidence/04_System_Tests/cross_user_test.md`
- Modify: `docs/evidence/02_Agent/follow_up_question_test.md`
- Modify: `docs/evidence/01_Prompts/prompt_record.md`

- [ ] **Step 1: Record the completed no-profile-data health check**

Record the loaded-key success and configured chat/embedding model IDs only. Never write the key, response ID, or provider object.

- [ ] **Step 2: Run all user-approved scenarios**

Run the five supplied profiles, complete/incomplete agent tests, same-profile two-job comparison, cross-session run, and unseen profile. Keep all actual outputs, including blocked exports.

- [ ] **Step 3: Repair observed defects only**

For an implementation or prompt failure, add a deterministic failing regression test first, implement the smallest fix, run offline checks, and rerun only the affected live scenario. Preserve both records.

- [ ] **Step 4: Derive Markdown evidence and run final gates**

Run backend pytest/Ruff/mypy; frontend contract, Vitest, ESLint, types, build, and Playwright; then `git diff --check`. Commit only redacted evidence that corresponds to actual records.

## Plan self-review

- The plan covers all requested profiles and scenarios, freezes expectations before retrieval, and separates harmless health access from profile-data calls.
- All new implementation is test-first; live behavior is recorded rather than asserted inside pytest.
- No planned artifact contains a key, raw provider response, or invented live result.
