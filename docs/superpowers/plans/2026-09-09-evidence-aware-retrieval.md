# Evidence-Aware Job Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add deterministic, evidence-aware job reranking above semantic retrieval, with structured job matching data and a frozen offline baseline.

**Architecture:** Existing embeddings provide broad recall. A pure-Python reranker combines each semantic score with project, skill, target-role, education, and explicit-experience evidence derived from confirmed facts and structured supplied job text. It returns a public breakdown and source-backed reasons while requirements remain separate evidence gaps.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, Ruff, mypy, React 19, TypeScript, Vitest, React Testing Library, Playwright, OpenAPI TypeScript.

**Spec:** docs/superpowers/specs/2026-09-09-evidence-aware-retrieval-design.md

## Global Constraints

- Do not mutate supplied data files or previously committed live-run artifacts.
- Use confirmed facts only; do not infer character, potential, seniority, eligibility, work rights, qualification completion, or experience.
- Mandatory requirements stay as evidence gaps; they are never a hidden rank penalty.
- Make no provider call, embedding request, live rerun, or API-key read during this plan.
- Keep embedding-cache behavior and document-ID tie-breaking deterministic.
- Do not add a model call, dependency, database, or external service.
- Regenerate OpenAPI client files with npm run contract:generate; never hand-edit generated files.
- Use npm test -- --run, not test:unit.
- Preserve the user-owned root .gitignore modification and do not stage it.

---

## File Structure

| File | Responsibility |
| --- | --- |
| docs/evidence/03_Retrieval/embedding_baseline_2026-09-07.json | Immutable pre-reranker results and development expectations. |
| scripts/verify_retrieval_baseline.py | Offline baseline integrity validator. |
| backend/app/domain/models.py | Public RetrievalScoreBreakdown schema. |
| backend/app/services/retrieval.py | Structured job representation, evidence scoring, reranking. |
| backend/tests/test_retrieval.py | Parser, scoring, safety, ordering, and cache tests. |
| backend/tests/test_retrieval_baseline.py | Historical baseline and fixed-vector comparison tests. |
| backend/tests/test_api.py | OpenAPI contract checks. |
| frontend/src/components/JobStage.tsx | Explainable score presentation. |
| frontend/src/App.test.tsx and frontend/e2e/workflow.spec.ts | Component and browser contract coverage. |
| docs/evidence/03_Retrieval/retrieval_results.md | Honest offline comparison and no-live-rerun boundary. |

## Task 1: Freeze and validate the embedding-only baseline

**Files:**
- Create: docs/evidence/03_Retrieval/embedding_baseline_2026-09-07.json
- Create: scripts/verify_retrieval_baseline.py
- Create: backend/tests/test_retrieval_baseline.py
- Modify: docs/evidence/03_Retrieval/retrieval_results.md

**Consumes:** historical artifacts under docs/evidence/06_Live_Evaluation/records/ and data/jobs.jsonl.

**Produces:** verify_retrieval_baseline(path: Path, jobs_path: Path) -> list[str].

- [ ] **Step 1: Write failing integrity tests**

~~~python
def test_committed_embedding_baseline_is_valid() -> None:
    assert verify_retrieval_baseline(BASELINE_PATH, JOBS_PATH) == [
        "student_profile_01", "student_profile_02", "student_profile_03",
        "student_profile_04", "student_profile_05", "unseen_profile_01",
    ]


def test_baseline_rejects_changed_job_hash(tmp_path: Path) -> None:
    altered = tmp_path / "jobs.jsonl"
    altered.write_text("changed corpus", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_retrieval_baseline(BASELINE_PATH, altered)
~~~

- [ ] **Step 2: Prove the tests fail**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval_baseline.py -q

Expected: FAIL because neither the JSON baseline nor verifier exists.

- [ ] **Step 3: Add immutable baseline data**

Use this exact top-level shape:

~~~json
{
  "schema_version": 1,
  "job_data_sha256": "0f9403de41f2de0605bbbf6ef3faa3a81f265b7ec36938aea6c058ada723b461",
  "source_artifacts": {
    "supplied_five": "docs/evidence/06_Live_Evaluation/records/supplied-five-initial/2026-09-07-152935354411-supplied-five.json",
    "unseen": "docs/evidence/06_Live_Evaluation/records/unseen-initial/2026-09-07-153114169436-unseen.json"
  },
  "profiles": []
}
~~~

Populate exactly six records. Each has profile_id, expected_document_id,
expectation_kind: development_expectation, and exactly three embedding_only_top_three
objects with document_id and observed semantic_score. Copy values directly from the
timestamped artifacts; do not recompute, round, or alter them. Label the vision case a
regression case, never held-out evidence.

- [ ] **Step 4: Implement the no-network verifier**

~~~python
def verify_retrieval_baseline(path: Path, jobs_path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document["schema_version"] != 1:
        raise ValueError("Unsupported retrieval baseline schema version.")
    actual_hash = sha256(jobs_path.read_bytes()).hexdigest()
    if actual_hash != document["job_data_sha256"]:
        raise ValueError("Job corpus SHA-256 does not match the frozen baseline.")
    known_ids = {job.document_id for job in JobRepository.load(jobs_path)}
    # Require six unique profile IDs, valid expected IDs, and three unique valid
    # ranked IDs for each profile before returning profile IDs in stored order.
~~~

Validate source-artifact paths relative to repository root. Add main() with --baseline
and --jobs; it prints only validated profile IDs and exits nonzero for ValueError.

- [ ] **Step 5: Add provenance note and verify**

Add a retrieval-evidence subsection linking the baseline, source artifacts, and corpus
SHA. State it is pre-reranker development evidence, no post-reranker live result exists,
and the previously viewed vision profile is not held-out.

Run:

~~~sh
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval_baseline.py -q
PYTHONPATH=backend .venv/bin/python scripts/verify_retrieval_baseline.py --baseline docs/evidence/03_Retrieval/embedding_baseline_2026-09-07.json --jobs data/jobs.jsonl
~~~

Expected: tests pass and six IDs print without a provider request.

- [ ] **Step 6: Commit**

~~~sh
git add docs/evidence/03_Retrieval/embedding_baseline_2026-09-07.json docs/evidence/03_Retrieval/retrieval_results.md scripts/verify_retrieval_baseline.py backend/tests/test_retrieval_baseline.py
git commit -m "test: freeze retrieval embedding baseline"
~~~

## Task 2: Add structured jobs and the public score contract

**Files:**
- Modify: backend/app/domain/models.py:69-88
- Modify: backend/app/services/retrieval.py:1-70
- Modify: backend/tests/test_retrieval.py
- Modify: backend/tests/test_api.py

**Consumes:** Job, confirmed Fact, and existing requirement parsing/token normalisation.

**Produces:** RetrievalScoreBreakdown, JobMatchProfile, and build_job_match_profile(job: Job) -> JobMatchProfile.

- [ ] **Step 1: Add failing parser/schema tests**

~~~python
def test_job_match_profile_preserves_sections_and_source_spans() -> None:
    job = Job(
        document_id="rag", title="AI Engineer",
        description=("About the role: Build applications. Responsibilities: Design RAG pipelines and AI-agent workflows. "
                     "Requirements: Python; RAG. Preferred experience includes LangChain."),
    )
    profile = build_job_match_profile(job)
    assert "rag" in profile.specialisation_terms
    assert profile.responsibility_spans == ("Design RAG pipelines and AI-agent workflows.",)
    assert profile.mandatory_requirement_spans == ("Python", "RAG")
    assert "LangChain" in profile.optional_requirement_spans[0]


def test_retrieval_result_requires_a_complete_score_breakdown() -> None:
    schema = RetrievalResult.model_json_schema()
    assert schema["properties"]["score_breakdown"]["$ref"].endswith("RetrievalScoreBreakdown")
~~~

- [ ] **Step 2: Prove they fail**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval.py -k 'match_profile or score_breakdown' -q

Expected: FAIL because types and structured parsing do not exist.

- [ ] **Step 3: Add the additive public model**

~~~python
class RetrievalScoreBreakdown(StrictModel):
    semantic_score: float = Field(ge=0.0, le=1.0)
    project_score: float = Field(ge=0.0, le=1.0)
    skill_score: float = Field(ge=0.0, le=1.0)
    target_role_score: float = Field(ge=0.0, le=1.0)
    education_score: float = Field(ge=0.0, le=1.0)
    experience_score: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
~~~

Add required score_breakdown: RetrievalScoreBreakdown to RetrievalResult. Retain score,
but set it to final_score and document it as a relevance score, preserving its API field name.
Before running this step's green suite, use rg to find every RetrievalResult(...) fixture in
backend/tests and update each fixture with a complete zero-or-explicit score_breakdown. Do not
make the field optional merely to preserve an old test.

- [ ] **Step 4: Implement pure structured job parsing**

Add this frozen internal dataclass in retrieval.py:

~~~python
@dataclass(frozen=True)
class JobMatchProfile:
    job: Job
    title_terms: frozenset[str]
    specialisation_terms: frozenset[str]
    responsibility_terms: frozenset[str]
    mandatory_requirement_terms: frozenset[str]
    optional_requirement_terms: frozenset[str]
    responsibility_spans: tuple[str, ...]
    mandatory_requirement_spans: tuple[str, ...]
    optional_requirement_spans: tuple[str, ...]
~~~

Recognise case-insensitive markers About the role:, Responsibilities:, Requirements:,
Minimum qualifications:, Preferred qualifications:, Preferred experience:, Nice to have:,
and Desirable experience. Retain exact trimmed spans. Derive terms through the existing
alias/noise pipeline; unknown text remains in the full embedding input.

- [ ] **Step 5: Verify and commit**

~~~sh
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval.py -k 'match_profile or score_breakdown or requirement_parser' -q
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_api.py -k openapi -q
git add backend/app/domain/models.py backend/app/services/retrieval.py backend/tests/test_retrieval.py backend/tests/test_api.py
git commit -m "feat: add structured job match profiles"
~~~

## Task 3: Implement deterministic evidence scoring and reranking

**Files:**
- Modify: backend/app/services/retrieval.py:70-260
- Modify: backend/tests/test_retrieval.py

**Consumes:** structured jobs, confirmed profiles, and existing cosine scores.

**Produces:** score_job_evidence(profile, job_profile, semantic_score) -> RetrievalScoreBreakdown and rerank_scored_jobs(profile, semantic_scores, job_profiles).

- [ ] **Step 1: Write failing safety and arithmetic tests**

~~~python
def test_project_signal_raises_rag_relevance_without_erasing_degree_gap() -> None:
    profile = ProfileDraft(facts=[
        confirmed_fact("project", "Built a retrieval-augmented assistant with embeddings and FAISS."),
        confirmed_fact("skills", "Python"),
    ])
    rag = build_job_match_profile(Job(
        document_id="rag", title="AI Engineer", description=RAG_DESCRIPTION,
    ))
    score = score_job_evidence(profile, rag, semantic_score=0.50)
    assert score.project_score > 0
    assert score.final_score == pytest.approx(0.55 * 0.50 + 0.45 * score.evidence_score)
    gaps = _missing_requirements(profile, rag.job)
    assert any("master's degree" in gap for gap in gaps)
    assert any("three or more years" in gap for gap in gaps)


def test_aspiration_and_generic_degree_do_not_score_as_vision_evidence() -> None:
    profile = ProfileDraft(facts=[
        confirmed_fact("education", "Bachelor of Computing Science"),
        confirmed_fact("project", "Interested in computer vision but no project experience"),
    ])
    vision = build_job_match_profile(Job(
        document_id="vision", title="Computer Vision Engineer",
        description="Responsibilities: Build computer-vision models. Requirements: OpenCV; Python.",
    ))
    assert score_job_evidence(profile, vision, semantic_score=0.5).project_score == 0
~~~

Also test that a declared skill does not become experience and a final-score tie sorts
by document_id.

- [ ] **Step 2: Prove failure**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval.py -k 'project_signal or aspiration or final_score_tie' -q

Expected: FAIL because scorer/reranker functions do not exist.

- [ ] **Step 3: Implement fixed-weight scoring**

Define module constants:

~~~python
SEMANTIC_WEIGHT = 0.55
EVIDENCE_WEIGHT = 0.45
PROJECT_WEIGHT = 0.40
SKILL_WEIGHT = 0.25
TARGET_ROLE_WEIGHT = 0.15
EDUCATION_WEIGHT = 0.10
EXPERIENCE_WEIGHT = 0.10
~~~

Implement overlap_score(candidate_terms, job_terms): zero for empty input, otherwise
intersection count divided by candidate-term count. Score projects against title +
specialisation + responsibilities; skills against title + specialisation + responsibilities
+ mandatory requirements; target role against title + specialisation; education against title
+ mandatory requirements; and experience against responsibilities + mandatory requirements.
Only the permitted fact fields contribute. Compute weighted evidence_score, then
final_score = 0.55 * semantic_score + 0.45 * evidence_score.

Build match_reasons from a non-zero component's actual fact field and overlap, e.g.
project: retrieval, embeddings -> RAG. Never call a reason an eligibility conclusion or claim
the embedding caused rank.

- [ ] **Step 4: Integrate into RetrievalService.retrieve**

Leave _get_job_vectors() unchanged. Cache
self._job_match_profiles: list[JobMatchProfile] | None, score all nine semantic candidates,
rerank by (-final_score, document_id), and return top top_k. Round only in the API result,
setting both score and score_breakdown.final_score to the rounded final value. Preserve exact
excerpt, matched skills, gaps, and eligibility note.

- [ ] **Step 5: Verify and commit**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval.py -q

Expected: old cache/provenance/gap tests and new reranking tests pass.

~~~sh
git add backend/app/services/retrieval.py backend/tests/test_retrieval.py
git commit -m "feat: rerank jobs with confirmed evidence"
~~~

## Task 4: Compare against the frozen baseline and regenerate the contract

**Files:**
- Modify: backend/tests/test_retrieval_baseline.py
- Modify: backend/tests/test_api.py
- Modify: frontend/openapi.json
- Modify: frontend/src/generated/api-schema.ts

**Consumes:** frozen JSON baseline and RetrievalService.

**Produces:** offline, reproducible rank-delta coverage and generated frontend types.

- [ ] **Step 1: Write a failing fixed-vector comparison test**

Create a test-only RecordedTopThreeEmbedder: nine jobs receive orthogonal vectors; each fixture
query gives the recorded top-three score coordinates and documented lower values for unobserved
fourth-to-ninth positions. Include a padding coordinate so cosine is valid. This is a top-three
regression fixture, not a claim that unobserved historic scores are known.

~~~python
def test_reranker_compares_with_frozen_embedding_baseline() -> None:
    service = RetrievalService(
        JobRepository.load(JOBS_PATH),
        RecordedTopThreeEmbedder(load_baseline(BASELINE_PATH)),
    )
    profile = imported_profile_from_data("student_profile_02", Path("data/student_profiles.jsonl"))
    results = service.retrieve(profile)
    assert len(results) == 3
    assert len({result.document_id for result in results}) == 3
    assert all(result.score == result.score_breakdown.final_score for result in results)
~~~

Test that this fixture reproduces stored old top three before final reranking, without creating
a production endpoint or provider dependency.
Define `imported_profile_from_data(profile_id: str, path: Path) -> ProfileDraft` in this test
module: load the matching JSONL row, map only its supplied profile fields to `Fact` instances
with `FactStatus.CONFIRMED` and `IMPORTED_TEST_PROFILE` source metadata, and raise `KeyError`
for an unknown profile ID. This keeps the comparison faithful to the supplied controlled input.

- [ ] **Step 2: Prove failure and add API assertions**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval_baseline.py -k reranker -q

Expected: FAIL until the fixture/comparison seam exists.

In test_api.py, require all eight RetrievalScoreBreakdown fields and the
RetrievalResult.score_breakdown OpenAPI reference.

- [ ] **Step 3: Regenerate and verify contract**

~~~sh
cd frontend && npm run contract:generate && cd ..
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_api.py backend/tests/test_retrieval_baseline.py -q
~~~

Expected: generated files change only for the additive breakdown schema; all tests remain offline.

- [ ] **Step 4: Commit**

~~~sh
git add backend/tests/test_retrieval_baseline.py backend/tests/test_api.py frontend/openapi.json frontend/src/generated/api-schema.ts
git commit -m "test: compare reranking with frozen baseline"
~~~

## Task 5: Explain relevance in React job cards

**Files:**
- Modify: frontend/src/components/JobStage.tsx
- Modify: frontend/src/App.test.tsx
- Modify: frontend/e2e/workflow.spec.ts
- Modify: frontend/src/styles.css only if compact-breakdown styling needs it.

**Consumes:** generated RetrievalResult.score_breakdown, source-backed match_reasons, existing gaps.

**Produces:** accessible relevance explanation that never implies eligibility.

- [ ] **Step 1: Write failing component test**

~~~tsx
it('shows relevance evidence while keeping requirements separate', () => {
  render(<WorkflowApp session={retrievedSessionWithBreakdown} {...callbacks} />)
  fireEvent.click(screen.getByRole('button', { name: /Job matches/ }))
  expect(screen.getByText('Relevance score')).toBeVisible()
  expect(screen.getByText('Project evidence')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Missing requirements' })).toBeVisible()
  expect(screen.queryByText(/eligibility probability/i)).not.toBeInTheDocument()
})
~~~

Update every TypeScript fixture with all eight required breakdown fields.

- [ ] **Step 2: Prove failure**

Run: cd frontend && npm test -- --run src/App.test.tsx

Expected: FAIL because JobStage does not render the breakdown.

- [ ] **Step 3: Implement compact evidence display**

Replace Similarity score with Relevance score. Add a details element named Why this ranked here
that shows Broad semantic similarity, Project evidence, Skills evidence, Target role, Education,
and Experience. Show match_reasons under Confirmed evidence signals. Keep the existing
missing-requirements panel and eligibility note verbatim. Use a scoped .relevance-breakdown rule
only if needed for mobile wrapping.

- [ ] **Step 4: Update browser fixtures and run UI checks**

Every mocked result in frontend/e2e/workflow.spec.ts receives a complete breakdown. The happy
path asserts Relevance score and Why this ranked here while retaining blocked-export,
profile-revision, provider-failure, and session-isolation assertions.

~~~sh
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
npx playwright test --workers=2
~~~

- [ ] **Step 5: Commit**

~~~sh
git add frontend/src/components/JobStage.tsx frontend/src/App.test.tsx frontend/e2e/workflow.spec.ts frontend/src/styles.css
git commit -m "feat: explain evidence-aware job rankings"
~~~

## Task 6: Record the offline result and final no-provider verification

**Files:**
- Modify: docs/evidence/03_Retrieval/retrieval_results.md
- Modify: docs/evidence/04_System_Tests/acceptance_coverage.md
- Modify: backend/tests/test_retrieval_baseline.py

**Consumes:** baseline, fixed-vector comparison, backend and frontend results.

**Produces:** accurate offline-only evidence and explicit live-rerun approval gate.

- [ ] **Step 1: Write failing evidence-wording test**

~~~python
def test_retrieval_evidence_states_the_offline_boundary() -> None:
    evidence = EVIDENCE_PATH.read_text(encoding="utf-8")
    assert "No post-reranker live evaluation has been run." in evidence
    assert "development expectations" in evidence
    assert "not an independent held-out benchmark" in evidence
~~~

- [ ] **Step 2: Prove failure**

Run: PYTHONPATH=backend .venv/bin/pytest backend/tests/test_retrieval_baseline.py -k offline_boundary -q

Expected: FAIL until evidence distinguishes fixture comparison from live results.

- [ ] **Step 3: Document observed offline behavior only**

Add a before/after table for baseline top three, fixed-vector reranker top three, and rank delta
for six profiles. Label output offline regression comparison. State exactly: no post-reranker
live evaluation has run; the six expectations are unchanged development expectations; vision is
a regression, not independent holdout; relevance is not eligibility; a billable rerun requires
new user approval. Update acceptance coverage with offline tests. Do not fabricate a
failure-and-repair entry if no real failure occurs.

- [ ] **Step 4: Run final no-provider gate**

~~~sh
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
.venv/bin/ruff check backend scripts/verify_retrieval_baseline.py
.venv/bin/mypy --config-file backend/pyproject.toml backend/app scripts/verify_retrieval_baseline.py
cd frontend
npm run contract:check
npm test -- --run
npm run lint
npm run typecheck
npm run build
npx playwright test --workers=2
cd ..
git diff --check
git status --short
~~~

Expected: every check passes without a provider request; Git status contains at most the
pre-existing .gitignore change.

- [ ] **Step 5: Commit**

~~~sh
git add docs/evidence/03_Retrieval/retrieval_results.md docs/evidence/04_System_Tests/acceptance_coverage.md backend/tests/test_retrieval_baseline.py
git commit -m "docs: record offline retrieval reranking evaluation"
~~~

## Post-Plan Decision Gate

Do not make a new live OpenAI retrieval automatically. Present the offline before/after table,
rank explanations, tests, and regressions to Luke. A separate explicitly approved live-evaluation
plan must preserve the original 2026-09-07 artifacts and record the reranker as a distinct
configuration.
