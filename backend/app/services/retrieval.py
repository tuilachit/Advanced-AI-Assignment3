from __future__ import annotations

import json
import math
import re
from collections.abc import Set
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.domain.models import (
    Fact,
    FactStatus,
    Job,
    ProfileDraft,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from app.domain.profile_fields import profile_field_category


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class JobDataError(ValueError):
    pass


class ProfileNotConfirmedError(ValueError):
    pass


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


class JobRepository:
    @staticmethod
    def default_data_path() -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "jobs.jsonl"

    @staticmethod
    def load(path: Path, *, expected_count: int = 9) -> list[Job]:
        try:
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            jobs = [Job.model_validate(row) for row in rows]
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise JobDataError(f"Unable to load valid jobs from {path}.") from error

        if len(jobs) != expected_count:
            raise JobDataError(f"Expected {expected_count} jobs, found {len(jobs)}.")
        if len({job.document_id for job in jobs}) != len(jobs):
            raise JobDataError("Job document IDs must be unique.")
        return jobs


PROFILE_FIELD_ORDER = (
    "target_role",
    "skills",
    "education",
    "experience",
    "project",
)

SEMANTIC_WEIGHT = 0.55
EVIDENCE_WEIGHT = 0.45
PROJECT_WEIGHT = 0.40
SKILL_WEIGHT = 0.25
TARGET_ROLE_WEIGHT = 0.15
EDUCATION_WEIGHT = 0.10
EXPERIENCE_WEIGHT = 0.10


def overlap_score(candidate_terms: Set[str], job_terms: Set[str]) -> float:
    if not candidate_terms or not job_terms:
        return 0.0
    return len(candidate_terms & job_terms) / len(candidate_terms)


def _ranking_terms(text: str) -> set[str]:
    return _evidence_tokens(text) - {"project", "role"}


def _job_terms_by_fact_field(job_profile: JobMatchProfile) -> dict[str, frozenset[str]]:
    domain_terms = job_profile.title_terms | job_profile.specialisation_terms
    project_terms = domain_terms | job_profile.responsibility_terms
    skill_terms = project_terms | job_profile.mandatory_requirement_terms
    return {
        "project": project_terms,
        "skills": skill_terms,
        "target_role": domain_terms,
        "education": job_profile.title_terms | job_profile.mandatory_requirement_terms,
        "experience": (job_profile.responsibility_terms | job_profile.mandatory_requirement_terms),
    }


def score_job_evidence(
    profile: ProfileDraft, job_profile: JobMatchProfile, semantic_score: float
) -> RetrievalScoreBreakdown:
    job_terms = _job_terms_by_fact_field(job_profile)
    candidate_terms: dict[str, set[str]] = {field: set() for field in job_terms}
    for fact in profile.facts:
        category = profile_field_category(fact.field)
        if category in candidate_terms and _fact_can_support_evidence(fact):
            candidate_terms[category].update(_ranking_terms(fact.value))

    project_score = overlap_score(candidate_terms["project"], job_terms["project"])
    skill_score = overlap_score(candidate_terms["skills"], job_terms["skills"])
    target_role_score = overlap_score(candidate_terms["target_role"], job_terms["target_role"])
    education_score = overlap_score(candidate_terms["education"], job_terms["education"])
    experience_score = overlap_score(candidate_terms["experience"], job_terms["experience"])
    evidence_score = (
        PROJECT_WEIGHT * project_score
        + SKILL_WEIGHT * skill_score
        + TARGET_ROLE_WEIGHT * target_role_score
        + EDUCATION_WEIGHT * education_score
        + EXPERIENCE_WEIGHT * experience_score
    )
    # Preserve the public score's bounded scale, without rounding before ranking.
    semantic_score = max(0.0, min(1.0, semantic_score))
    return RetrievalScoreBreakdown(
        semantic_score=semantic_score,
        project_score=project_score,
        skill_score=skill_score,
        target_role_score=target_role_score,
        education_score=education_score,
        experience_score=experience_score,
        evidence_score=evidence_score,
        final_score=SEMANTIC_WEIGHT * semantic_score + EVIDENCE_WEIGHT * evidence_score,
    )


def rerank_scored_jobs(
    profile: ProfileDraft,
    semantic_scores: list[float],
    job_profiles: list[JobMatchProfile],
) -> list[tuple[RetrievalScoreBreakdown, JobMatchProfile]]:
    scored = [
        (score_job_evidence(profile, job_profile, semantic_score), job_profile)
        for semantic_score, job_profile in zip(semantic_scores, job_profiles, strict=True)
    ]
    return sorted(scored, key=lambda item: (-item[0].final_score, item[1].job.document_id))


def build_profile_query(profile: ProfileDraft) -> str:
    confirmed = [
        (category, fact.field, fact.value)
        for fact in profile.facts
        if fact.status is FactStatus.CONFIRMED
        and (category := profile_field_category(fact.field)) is not None
        and category != "name"
    ]
    order = {field: index for index, field in enumerate(PROFILE_FIELD_ORDER)}
    confirmed.sort(key=lambda item: (order.get(item[0], len(order)), *item))
    return "\n".join(f"{category}: {value}" for category, _field, value in confirmed)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have equal dimensions.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


class RetrievalService:
    def __init__(self, jobs: list[Job], embedder: EmbeddingProvider) -> None:
        self._jobs = jobs
        self._embedder = embedder
        self._job_vectors: list[list[float]] | None = None
        self._job_match_profiles: list[JobMatchProfile] | None = None

    def retrieve(self, profile: ProfileDraft, *, top_k: int = 3) -> list[RetrievalResult]:
        if not profile.facts or any(
            fact.status is not FactStatus.CONFIRMED for fact in profile.facts
        ):
            raise ProfileNotConfirmedError("Job retrieval requires a confirmed profile.")
        query = build_profile_query(profile)
        if not query:
            raise ProfileNotConfirmedError("The confirmed profile has no searchable facts.")

        job_vectors = self._get_job_vectors()
        query_vector = self._embedder.embed([query])[0]
        semantic_scores = [cosine_similarity(vector, query_vector) for vector in job_vectors]
        if self._job_match_profiles is None:
            self._job_match_profiles = [build_job_match_profile(job) for job in self._jobs]
        scored = rerank_scored_jobs(profile, semantic_scores, self._job_match_profiles)

        results: list[RetrievalResult] = []
        for breakdown, job_profile in scored[: min(top_k, len(scored))]:
            job = job_profile.job
            rounded_breakdown = RetrievalScoreBreakdown.model_validate(
                {field: _bounded_score(value) for field, value in breakdown.model_dump().items()}
            )
            results.append(
                RetrievalResult(
                    document_id=job.document_id,
                    title=job.title,
                    score=rounded_breakdown.final_score,
                    score_breakdown=rounded_breakdown,
                    excerpt=_best_exact_excerpt(job.description, query),
                    match_reasons=_match_reasons(profile, job, job_profile=job_profile),
                    matched_skills=_matched_skills(profile, job),
                    missing_requirements=_missing_requirements(profile, job),
                    eligibility_notes=[
                        "Relevance and evidence gaps do not decide eligibility; "
                        "verify the full job record."
                    ],
                )
            )
        return results

    def _get_job_vectors(self) -> list[list[float]]:
        if self._job_vectors is None:
            texts = [f"{job.title}\n{job.description}" for job in self._jobs]
            self._job_vectors = self._embedder.embed(texts)
            if len(self._job_vectors) != len(self._jobs):
                raise ValueError("Embedding provider returned the wrong number of vectors.")
        return self._job_vectors


def _bounded_score(score: float) -> float:
    return round(max(0.0, min(1.0, score)), 6)


def _tokens(text: str) -> set[str]:
    return {
        cleaned
        for token in re.findall(r"[a-z0-9+#.]+", text.lower())
        if len(cleaned := token.strip(".")) > 2
    }


def _best_exact_excerpt(description: str, query: str) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", description) if part]
    if not sentences:
        return description
    query_tokens = _tokens(query)
    return max(
        sentences,
        key=lambda sentence: (len(_tokens(sentence) & query_tokens), -len(sentence)),
    )


def _match_reasons(
    profile: ProfileDraft, job: Job, *, job_profile: JobMatchProfile | None = None
) -> list[str]:
    job_terms = _job_terms_by_fact_field(job_profile or build_job_match_profile(job))
    reasons: list[str] = []
    for fact in profile.facts:
        category = profile_field_category(fact.field)
        if category not in job_terms or not _fact_can_support_evidence(fact):
            continue
        overlap = sorted(_ranking_terms(fact.value) & job_terms[category])
        if overlap:
            reasons.append(f"{fact.field}: {', '.join(overlap[:5])}")
    return reasons[:3]


def _matched_skills(profile: ProfileDraft, job: Job) -> list[str]:
    job_tokens = _evidence_tokens(f"{job.title} {job.description}")
    matched: list[str] = []
    for fact in profile.facts:
        if profile_field_category(fact.field) == "skills" and _fact_can_support_evidence(fact):
            for skill in re.split(r"\s*(?:[,;\n]|\band\b)\s*", fact.value):
                cleaned = skill.strip()
                skill_tokens = _evidence_tokens(cleaned)
                if cleaned and skill_tokens and skill_tokens <= job_tokens:
                    matched.append(cleaned)
    return list(dict.fromkeys(matched))


def _missing_requirements(profile: ProfileDraft, job: Job) -> list[str]:
    requirements = _requirement_items(job.description)
    if not requirements:
        return []
    missing = [
        requirement
        for requirement in requirements
        if not _has_confirmed_evidence(requirement, profile)
    ]
    return missing


_TOKEN_ALIASES = {
    "apis": "api",
    "agents": "agent",
    "llms": "llm",
    "models": "model",
    "systems": "system",
}
_EVIDENCE_NOISE = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "into",
    "related",
    "strong",
    "knowledge",
    "ability",
    "skills",
    "skill",
    "experience",
    "professional",
    "industry",
    "framework",
    "frameworks",
    "similar",
    "such",
    "technologies",
    "technology",
    "up",
    "year",
    "years",
}
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_EVIDENCE_NOISE.update(_NUMBER_WORDS)

_ASPIRATION_OR_NEGATION = re.compile(
    r"\b(?:no|not|never|without|lacks?|lacking)\b|"
    r"\b[a-z]+n['’]t\b|"
    r"\b(?:interested in|hop(?:e|es|ed|ing) to|want(?:s|ed|ing)? to|"
    r"would like to|currently learning|plan(?:s|ned|ning)? (?:to|on)|"
    r"intend(?:s|ed|ing)? to|aim(?:s|ed|ing)? to|aspir(?:e|es|ed|ing) to|"
    r"looking to)\b",
    flags=re.IGNORECASE,
)


def _fact_can_support_evidence(fact: Fact) -> bool:
    return (
        fact.status is FactStatus.CONFIRMED
        and _ASPIRATION_OR_NEGATION.search(fact.value) is None
    )


def _evidence_tokens(text: str) -> set[str]:
    tokens = _tokens(text)
    normalised = {_TOKEN_ALIASES.get(token, token) for token in tokens}
    return normalised - _EVIDENCE_NOISE


_JOB_SECTION_MARKER = re.compile(
    r"\b(?P<name>About the role|Responsibilities|Requirements|"
    r"Minimum qualifications|Preferred qualifications|Preferred experience|"
    r"Nice to have|Desirable experience)(?:\s*:\s*|\s+includes\s+)",
    flags=re.IGNORECASE,
)

_RESPONSIBILITY_SECTIONS = frozenset({"responsibilities"})
_OPTIONAL_SECTIONS = frozenset(
    {
        "preferred qualifications",
        "preferred experience",
        "nice to have",
        "desirable experience",
    }
)


def _job_sections(description: str) -> list[tuple[str, str]]:
    markers = list(_JOB_SECTION_MARKER.finditer(description))
    return [
        (
            marker.group("name").lower(),
            description[
                marker.end() : markers[index + 1].start()
                if index + 1 < len(markers)
                else len(description)
            ].strip(),
        )
        for index, marker in enumerate(markers)
    ]


def _sentence_spans(text: str) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    )


def build_job_match_profile(job: Job) -> JobMatchProfile:
    sections = _job_sections(job.description)
    role_text = " ".join(
        content for name, content in sections if name == "about the role"
    )
    responsibility_spans = tuple(
        span
        for name, content in sections
        if name in _RESPONSIBILITY_SECTIONS
        for span in _sentence_spans(content)
    )
    mandatory_requirement_spans = tuple(_requirement_items(job.description))
    optional_requirement_spans = tuple(
        span
        for name, content in sections
        if name in _OPTIONAL_SECTIONS
        for span in _sentence_spans(content)
    )
    title_terms = frozenset(_evidence_tokens(job.title))
    responsibility_terms = frozenset(
        _evidence_tokens(" ".join(responsibility_spans))
    )

    return JobMatchProfile(
        job=job,
        title_terms=title_terms,
        specialisation_terms=frozenset(
            title_terms | _evidence_tokens(role_text) | responsibility_terms
        ),
        responsibility_terms=responsibility_terms,
        mandatory_requirement_terms=frozenset(
            _evidence_tokens(" ".join(mandatory_requirement_spans))
        ),
        optional_requirement_terms=frozenset(
            _evidence_tokens(" ".join(optional_requirement_spans))
        ),
        responsibility_spans=responsibility_spans,
        mandatory_requirement_spans=mandatory_requirement_spans,
        optional_requirement_spans=optional_requirement_spans,
    )


def _years_mentioned(text: str) -> int | None:
    match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"(?:\s+to\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))?"
        r"(?:\s+or\s+more)?\s+years?\b",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    value = match.group(1).lower()
    return int(value) if value.isdigit() else _NUMBER_WORDS[value]


def _alternative_token_groups(requirement: str) -> list[set[str]]:
    alternatives = requirement
    for marker in ("at least one of", "such as"):
        if marker in alternatives.lower():
            alternatives = re.split(marker, alternatives, maxsplit=1, flags=re.IGNORECASE)[1]
            break
    choices = re.split(r"\s*,\s*(?:or\s+)?|\s+or\s+", alternatives, flags=re.IGNORECASE)
    return [tokens for choice in choices if (tokens := _evidence_tokens(choice))]


def _has_confirmed_evidence(requirement: str, profile: ProfileDraft) -> bool:
    evidence_facts = [
        fact
        for fact in profile.facts
        if _fact_can_support_evidence(fact)
        and profile_field_category(fact.field)
        in {
            "education",
            "skills",
            "experience",
            "project",
            "achievement",
            "activity",
            "certification",
        }
    ]
    evidence_text = " ".join(fact.value for fact in evidence_facts)
    required_years = _years_mentioned(requirement)
    if required_years is not None:
        requirement_domain = _evidence_tokens(requirement)
        maximum_constraint = re.search(r"\bup to\b", requirement, re.IGNORECASE) is not None
        return any(
            (stated_years := _years_mentioned(fact.value)) is not None
            and (
                stated_years <= required_years
                if maximum_constraint
                else stated_years >= required_years
            )
            and (not requirement_domain or bool(requirement_domain & _evidence_tokens(fact.value)))
            for fact in evidence_facts
            if profile_field_category(fact.field) == "experience"
        )

    lowered = requirement.lower()
    education_text = " ".join(
        fact.value.lower()
        for fact in evidence_facts
        if profile_field_category(fact.field) == "education"
    )
    if "master's degree" in lowered or "masters degree" in lowered:
        has_level = any(level in education_text for level in ("master", "phd", "doctor"))
        fields = _evidence_tokens(requirement) - {"master", "masters", "degree", "above"}
        return has_level and bool(fields & _evidence_tokens(education_text))
    if "degree" in lowered:
        has_degree = any(
            level in education_text for level in ("bachelor", "degree", "master", "phd", "doctor")
        )
        fields = _evidence_tokens(requirement) - {
            "degree",
            "field",
            "higher",
            "recent",
            "completion",
        }
        return has_degree and bool(fields & _evidence_tokens(education_text))

    required_tokens = _evidence_tokens(requirement)
    if not required_tokens:
        return False
    evidence_tokens = _evidence_tokens(evidence_text)
    if "at least one of" in lowered or " or " in lowered:
        return any(
            alternative <= evidence_tokens
            for alternative in _alternative_token_groups(requirement)
        )
    return required_tokens <= evidence_tokens


def _requirement_items(description: str) -> list[str]:
    marker = re.search(
        r"\b(?:Requirements|Minimum qualifications):\s*(.+)$",
        description,
        flags=re.IGNORECASE,
    )
    if marker is None:
        return []
    requirements_text = re.split(
        r"\b(?:Preferred qualifications|Preferred experience|Nice to have|"
        r"Desirable experience)(?:\s+includes)?\s*:?",
        marker.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    items: list[str] = []
    for item in requirements_text.split(";"):
        items.extend(re.split(r",?\s+together with\s+", item, flags=re.IGNORECASE))
    return [
        item.strip().removeprefix("and ").rstrip(".")
        for item in items
        if item.strip()
    ]
