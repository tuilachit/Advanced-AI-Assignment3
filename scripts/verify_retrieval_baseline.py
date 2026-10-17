"""Validate the frozen embedding-only retrieval baseline without provider access."""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.services.retrieval import JobRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PROFILE_COUNT = 6
EXPECTED_TOP_THREE_COUNT = 3


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Frozen baseline {field_name} must be a non-empty string.")
    return value


def _validate_source_artifacts(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"supplied_five", "unseen"}:
        raise ValueError("Frozen baseline source artifacts are invalid.")
    for source_path in value.values():
        relative_path = Path(_required_string(source_path, "source artifact path"))
        if relative_path.is_absolute():
            raise ValueError("Frozen baseline source artifact paths must be repository-relative.")
        resolved_path = (REPOSITORY_ROOT / relative_path).resolve()
        if REPOSITORY_ROOT not in resolved_path.parents or not resolved_path.is_file():
            raise ValueError("Frozen baseline source artifact path does not exist in the repository.")


def verify_retrieval_baseline(path: Path, jobs_path: Path) -> list[str]:
    """Return validated profile IDs in frozen order, without embedding or provider calls."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Unable to load the frozen retrieval baseline.") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported retrieval baseline schema version.")
    actual_hash = sha256(jobs_path.read_bytes()).hexdigest()
    if actual_hash != document.get("job_data_sha256"):
        raise ValueError("Job corpus SHA-256 does not match the frozen baseline.")
    _validate_source_artifacts(document.get("source_artifacts"))
    known_ids = {job.document_id for job in JobRepository.load(jobs_path)}
    profiles = document.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != EXPECTED_PROFILE_COUNT:
        raise ValueError("Frozen baseline must contain exactly six profiles.")
    profile_ids: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Frozen baseline profile record is invalid.")
        profile_id = _required_string(profile.get("profile_id"), "profile_id")
        if profile_id in profile_ids:
            raise ValueError("Frozen baseline profile IDs must be unique.")
        profile_ids.append(profile_id)
        expected_document_id = _required_string(profile.get("expected_document_id"), "expected_document_id")
        if expected_document_id not in known_ids:
            raise ValueError("Frozen baseline expected document ID is not in the job corpus.")
        if profile.get("expectation_kind") != "development_expectation":
            raise ValueError("Frozen baseline expectations must be development expectations.")
        ranked = profile.get("embedding_only_top_three")
        if not isinstance(ranked, list) or len(ranked) != EXPECTED_TOP_THREE_COUNT:
            raise ValueError("Each frozen baseline profile must contain exactly three rankings.")
        ranked_ids: set[str] = set()
        for entry in ranked:
            if not isinstance(entry, dict):
                raise ValueError("Frozen baseline ranking record is invalid.")
            document_id = _required_string(entry.get("document_id"), "ranked document_id")
            score = entry.get("observed_semantic_score")
            if document_id not in known_ids or document_id in ranked_ids:
                raise ValueError("Frozen baseline ranked document IDs must be unique corpus IDs.")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
                raise ValueError("Frozen baseline semantic scores must be numbers between zero and one.")
            ranked_ids.add(document_id)
    return profile_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    args = parser.parse_args()
    try:
        for profile_id in verify_retrieval_baseline(args.baseline, args.jobs):
            print(profile_id)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
