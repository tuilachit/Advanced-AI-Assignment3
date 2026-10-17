import json
from itertools import combinations
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pytest

from app.domain.models import FactSourceType, FactStatus, ProfileDraft
from app.services.live_evaluation import profile_to_confirmed_facts
from app.services.retrieval import (
    JobRepository,
    RetrievalService,
    build_profile_query,
    cosine_similarity,
)

ROOT = Path(__file__).resolve().parents[2]
verify_retrieval_baseline = run_path(
    str(ROOT / "scripts/verify_retrieval_baseline.py")
)["verify_retrieval_baseline"]


BASELINE_PATH = ROOT / "docs/evidence/03_Retrieval/embedding_baseline_2026-09-07.json"
EVIDENCE_PATH = ROOT / "docs/evidence/03_Retrieval/retrieval_results.md"
JOBS_PATH = ROOT / "data/jobs.jsonl"
PROFILES_PATH = ROOT / "data/student_profiles.jsonl"
VISION_PROFILE_PATH = (
    ROOT / "docs/evidence/04_System_Tests/test_profiles/unseen_profile_01.json"
)


def load_baseline(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def imported_profile_from_data(profile_id: str, path: Path) -> ProfileDraft:
    rows = [
        cast(dict[str, object], json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    try:
        row = next(row for row in rows if row.get("document_id") == profile_id)
    except StopIteration:
        raise KeyError(profile_id) from None
    return ProfileDraft(facts=profile_to_confirmed_facts(row, profile_id))


def imported_baseline_profile(profile_id: str) -> ProfileDraft:
    if profile_id == "unseen_profile_01":
        row = json.loads(VISION_PROFILE_PATH.read_text(encoding="utf-8"))
        if row["document_id"] != profile_id:
            raise ValueError("Vision fixture document ID does not match the baseline.")
        return ProfileDraft(facts=profile_to_confirmed_facts(row, profile_id))
    return imported_profile_from_data(profile_id, PROFILES_PATH)


class RecordedTopThreeEmbedder:
    """Reproduce recorded ranks without treating unknown historic scores as observations.

    Job vectors use distinct basis coordinates. A query places the three observed
    semantic scores in those coordinates and assigns every unobserved job one
    synthetic coordinate just below the recorded third place. The final coordinate
    is padding, so every query remains non-zero. Cosine normalization changes the
    coordinate magnitudes but preserves their embedding-only order; this fixture
    therefore compares ranks, not purported historic scores outside the top three.
    """

    SYNTHETIC_LOWER_MARGIN = 0.000001
    QUERY_PADDING_COORDINATE = 1.0

    def __init__(self, baseline: dict[str, Any]) -> None:
        self._jobs = JobRepository.load(JOBS_PATH)
        self._job_texts = [f"{job.title}\n{job.description}" for job in self._jobs]
        records = cast(list[dict[str, Any]], baseline["profiles"])
        self._record_by_query: dict[str, dict[str, Any]] = {}
        for record in records:
            profile_id = cast(str, record["profile_id"])
            profile = imported_baseline_profile(profile_id)
            query = build_profile_query(profile)
            if query in self._record_by_query:
                raise ValueError("Recorded fixture queries must be unique.")
            self._record_by_query[query] = record

    def embed(self, texts: list[str]) -> list[list[float]]:
        dimension = len(self._jobs) + 1
        if texts == self._job_texts:
            return [
                [1.0 if coordinate == job_index else 0.0 for coordinate in range(dimension)]
                for job_index in range(len(self._jobs))
            ]
        if len(texts) != 1 or texts[0] not in self._record_by_query:
            raise AssertionError("Unexpected fixed-vector embedding request.")

        record = self._record_by_query[texts[0]]
        ranked = cast(list[dict[str, Any]], record["embedding_only_top_three"])
        recorded_scores = {
            cast(str, entry["document_id"]): float(entry["observed_semantic_score"])
            for entry in ranked
        }
        synthetic_lower_coordinate = (
            min(recorded_scores.values()) - self.SYNTHETIC_LOWER_MARGIN
        )
        if synthetic_lower_coordinate < 0:
            raise ValueError("Recorded scores leave no lower non-negative fixture coordinate.")
        return [
            [
                recorded_scores.get(job.document_id, synthetic_lower_coordinate)
                for job in self._jobs
            ]
            + [self.QUERY_PADDING_COORDINATE]
        ]


def test_committed_embedding_baseline_is_valid() -> None:
    assert verify_retrieval_baseline(BASELINE_PATH, JOBS_PATH) == [
        "student_profile_01",
        "student_profile_02",
        "student_profile_03",
        "student_profile_04",
        "student_profile_05",
        "unseen_profile_01",
    ]


def test_baseline_rejects_changed_job_hash(tmp_path: Path) -> None:
    altered = tmp_path / "jobs.jsonl"
    altered.write_text("changed corpus", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        verify_retrieval_baseline(BASELINE_PATH, altered)


def test_retrieval_evidence_preserves_live_and_offline_boundaries() -> None:
    evidence = EVIDENCE_PATH.read_text(encoding="utf-8")

    assert "Post-reranker live evaluation — 2026-09-09" in evidence
    assert "six expectations remained" in evidence
    assert "unchanged; no ranking logic" in evidence
    assert "not an independent held-out" in evidence
    assert "Observed top-1 agreement was 2/6" in evidence
    assert "top-3 inclusion was 4/6" in evidence


@pytest.mark.parametrize(
    ("profile_id", "expected_fixture_order"),
    [
        ("student_profile_01", [
            "trust_safety_ml_engineer", "rag_agent_engineer", "computer_vision_engineer",
        ]),
        ("student_profile_02", [
            "graduate_ai_engineer", "trust_safety_ml_engineer", "agentic_ai_data_scientist",
        ]),
        ("student_profile_03", [
            "graduate_ai_engineer", "agentic_ai_data_scientist", "nlp_multimodal_ml_engineer",
        ]),
        ("student_profile_04", [
            "agentic_ai_engineer", "healthcare_ml_engineer", "graduate_ai_engineer",
        ]),
        ("student_profile_05", [
            "graduate_ai_engineer", "rag_agent_engineer", "agentic_ai_engineer",
        ]),
        ("unseen_profile_01", [
            "computer_vision_engineer", "graduate_ai_engineer", "trust_safety_ml_engineer",
        ]),
    ],
)
def test_reranker_compares_with_frozen_embedding_baseline(
    profile_id: str, expected_fixture_order: list[str],
) -> None:
    baseline = load_baseline(BASELINE_PATH)
    profile = imported_baseline_profile(profile_id)
    jobs = JobRepository.load(JOBS_PATH)
    embedder = RecordedTopThreeEmbedder(baseline)

    job_vectors = embedder.embed([f"{job.title}\n{job.description}" for job in jobs])
    query_vector = embedder.embed([build_profile_query(profile)])[0]
    embedding_only_top_three = [
        job.document_id
        for _score, job in sorted(
            (
                (cosine_similarity(job_vector, query_vector), job)
                for job_vector, job in zip(job_vectors, jobs, strict=True)
            ),
            key=lambda item: (-item[0], item[1].document_id),
        )[:3]
    ]
    baseline_record = next(
        record for record in baseline["profiles"] if record["profile_id"] == profile_id
    )
    recorded_top_three = [
        entry["document_id"] for entry in baseline_record["embedding_only_top_three"]
    ]
    recorded_scores = {
        entry["document_id"]: entry["observed_semantic_score"]
        for entry in baseline_record["embedding_only_top_three"]
    }
    synthetic_lower_coordinate = (
        min(recorded_scores.values()) - RecordedTopThreeEmbedder.SYNTHETIC_LOWER_MARGIN
    )

    assert len(job_vectors) == 9
    assert all(
        cosine_similarity(left, right) == 0.0
        for left, right in combinations(job_vectors, 2)
    )
    assert query_vector[-1] == RecordedTopThreeEmbedder.QUERY_PADDING_COORDINATE
    assert all(
        query_vector[index]
        == recorded_scores.get(job.document_id, synthetic_lower_coordinate)
        for index, job in enumerate(jobs)
    )
    assert embedding_only_top_three == recorded_top_three

    results = RetrievalService(jobs, RecordedTopThreeEmbedder(baseline)).retrieve(profile)
    assert len(results) == 3
    assert len({result.document_id for result in results}) == 3
    # This is a deterministic rank delta under the documented synthetic
    # remainder, not a post-reranker live result.
    reranked_document_ids = [result.document_id for result in results]
    assert reranked_document_ids == expected_fixture_order
    assert all(result.score == result.score_breakdown.final_score for result in results)
    # Keep the published six-row comparison reproducible. These pinned outputs
    # describe this synthetic fixture, not the frozen human development expectations.
    documented_ranking = " > ".join(f"`{document_id}`" for document_id in reranked_document_ids)
    evidence_row = next(
        line for line in EVIDENCE_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"| `{profile_id}` |") and " > " in line
    )
    assert evidence_row.split("|")[3].strip() == documented_ranking


def test_imported_profile_requires_a_known_supplied_profile() -> None:
    profile = imported_profile_from_data("student_profile_02", PROFILES_PATH)

    assert profile.facts
    assert all(fact.status is FactStatus.CONFIRMED for fact in profile.facts)
    assert all(
        fact.source.source_type is FactSourceType.IMPORTED_TEST_PROFILE
        and fact.source.reference == "student_profile_02"
        for fact in profile.facts
    )
    with pytest.raises(KeyError, match="not_in_supplied_data"):
        imported_profile_from_data("not_in_supplied_data", PROFILES_PATH)
