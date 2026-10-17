import json
from pathlib import Path

import pytest

from app.domain.models import (
    Fact,
    FactSource,
    FactSourceType,
    FactStatus,
    Job,
    ProfileDraft,
    RetrievalResult,
)
from app.services import retrieval
from app.services.retrieval import (
    JobDataError,
    JobRepository,
    ProfileNotConfirmedError,
    RetrievalService,
    _match_reasons,
    _matched_skills,
    _missing_requirements,
    _requirement_items,
    build_job_match_profile,
    build_profile_query,
)


class KeywordEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [
            [
                float("python" in text.lower()),
                float("api" in text.lower()),
                float("vision" in text.lower()),
            ]
            for text in texts
        ]


def confirmed_fact(field: str, value: str) -> Fact:
    return Fact(
        field=field,
        value=value,
        status=FactStatus.CONFIRMED,
        source=FactSource(source_type=FactSourceType.USER_MESSAGE, reference="message-1"),
    )


RAG_DESCRIPTION = (
    "Responsibilities: Build retrieval-augmented assistants with embeddings and FAISS. "
    "Requirements: Python; a master's degree in computer science; "
    "three or more years of professional Python experience."
)


def test_project_signal_raises_rag_relevance_without_erasing_degree_gap() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed_fact(
                "project", "Built a retrieval-augmented assistant with embeddings and FAISS."
            ),
            confirmed_fact("skills", "Python"),
        ]
    )
    rag = build_job_match_profile(
        Job(
            document_id="rag",
            title="AI Engineer",
            description=RAG_DESCRIPTION,
        )
    )

    score = retrieval.score_job_evidence(profile, rag, semantic_score=0.50)

    assert score.project_score > 0
    assert score.final_score == pytest.approx(0.55 * 0.50 + 0.45 * score.evidence_score)
    gaps = _missing_requirements(profile, rag.job)
    assert any("master's degree" in gap for gap in gaps)
    assert any("three or more years" in gap for gap in gaps)


def test_aspiration_and_generic_degree_do_not_score_as_vision_evidence() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed_fact("education", "Bachelor of Computing Science"),
            confirmed_fact("project", "Interested in computer vision but no project experience"),
        ]
    )
    vision = build_job_match_profile(
        Job(
            document_id="vision",
            title="Computer Vision Engineer",
            description=(
                "Responsibilities: Build computer-vision models. Requirements: OpenCV; Python."
            ),
        )
    )

    assert retrieval.score_job_evidence(profile, vision, semantic_score=0.5).project_score == 0


@pytest.mark.parametrize(
    ("field", "component", "evidence_score", "final_score"),
    [
        ("project", "project_score", 0.40, 0.455),
        ("skills", "skill_score", 0.25, 0.3875),
        ("technical_skills", "skill_score", 0.25, 0.3875),
        ("target_role", "target_role_score", 0.15, 0.3425),
        ("education", "education_score", 0.10, 0.32),
        ("experience", "experience_score", 0.10, 0.32),
    ],
)
def test_evidence_arithmetic_keeps_fact_fields_separate(
    field: str, component: str, evidence_score: float, final_score: float
) -> None:
    profile = ProfileDraft(facts=[confirmed_fact(field, "Python")])
    job_profile = build_job_match_profile(
        Job(
            document_id="python",
            title="Python",
            description="Responsibilities: Python. Requirements: Python.",
        )
    )

    score = retrieval.score_job_evidence(profile, job_profile, semantic_score=0.5)

    assert getattr(score, component) == 1.0
    for other in {
        "project_score",
        "skill_score",
        "target_role_score",
        "education_score",
        "experience_score",
    } - {component}:
        assert getattr(score, other) == 0.0
    assert score.semantic_score == 0.5
    assert score.evidence_score == pytest.approx(evidence_score)
    assert score.final_score == pytest.approx(final_score)


@pytest.mark.parametrize(
    ("field", "title", "description"),
    [
        ("project", "Engineer", "Requirements: Python."),
        ("skills", "Engineer", "Preferred qualifications: Python."),
        ("target_role", "Engineer", "Requirements: Python."),
        ("education", "Engineer", "Responsibilities: Python."),
        ("experience", "Python Engineer", "Requirements: SQL."),
    ],
)
def test_evidence_uses_only_the_permitted_job_sections(
    field: str, title: str, description: str
) -> None:
    profile = ProfileDraft(facts=[confirmed_fact(field, "Python")])
    job_profile = build_job_match_profile(
        Job(
            document_id="job",
            title=title,
            description=description,
        )
    )

    assert retrieval.score_job_evidence(profile, job_profile, 0.5).evidence_score == 0.0


@pytest.mark.parametrize("field", ["summary", "name", "project_goal", "work_rights"])
def test_unknown_fields_do_not_contribute_evidence(field: str) -> None:
    profile = ProfileDraft(facts=[confirmed_fact(field, "Python")])
    job_profile = build_job_match_profile(
        Job(
            document_id="job",
            title="Python",
            description="Responsibilities: Python.",
        )
    )

    assert retrieval.score_job_evidence(profile, job_profile, 0.5).evidence_score == 0.0


def test_unconfirmed_and_negated_facts_do_not_contribute_evidence() -> None:
    draft = confirmed_fact("skills", "Python")
    draft.status = FactStatus.DRAFT
    profile = ProfileDraft(facts=[draft, confirmed_fact("experience", "No Python experience")])
    job_profile = build_job_match_profile(
        Job(
            document_id="job",
            title="Python",
            description="Responsibilities: Python.",
        )
    )

    assert retrieval.score_job_evidence(profile, job_profile, 0.5).evidence_score == 0.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project", "Planning to build computer vision models using OpenCV"),
        ("project", "I plan to build computer vision models using OpenCV"),
        ("project", "I am planning on building computer vision models using OpenCV"),
        ("project", "I intend to build computer vision models using OpenCV"),
        ("project", "I aim to build computer vision models using OpenCV"),
        ("project", "I hope to build computer vision models using OpenCV"),
        ("project", "I aspire to build computer vision models using OpenCV"),
        ("project", "Looking to build computer vision models using OpenCV"),
        ("experience", "I haven't used OpenCV"),
        ("experience", "I haven’t used OpenCV"),
        ("experience", "I didn't build computer vision models using OpenCV"),
        ("experience", "I don't have OpenCV experience"),
        ("experience", "I can’t build computer vision models using OpenCV"),
        ("experience", "I won’t use OpenCV"),
    ],
)
def test_planning_and_contracted_negation_cannot_score_or_explain_matches(
    field: str, value: str
) -> None:
    profile = ProfileDraft(facts=[confirmed_fact(field, value)])
    job = Job(
        document_id="vision",
        title="Computer Vision Engineer",
        description=(
            "Responsibilities: Build computer vision models using OpenCV. Requirements: OpenCV."
        ),
    )

    score = retrieval.score_job_evidence(profile, build_job_match_profile(job), 0.5)

    assert score.project_score == 0.0
    assert score.experience_score == 0.0
    assert score.evidence_score == 0.0
    assert score.final_score == 0.275
    assert _match_reasons(profile, job) == []
    assert _missing_requirements(profile, job) == ["OpenCV"]


@pytest.mark.parametrize("field", ["project", "experience"])
def test_completed_planning_and_building_still_supports_evidence(field: str) -> None:
    profile = ProfileDraft(
        facts=[confirmed_fact(field, "Planned and built computer vision models using OpenCV")]
    )
    job = Job(
        document_id="vision",
        title="Computer Vision Engineer",
        description=(
            "Responsibilities: Build computer vision models using OpenCV. Requirements: OpenCV."
        ),
    )

    score = retrieval.score_job_evidence(profile, build_job_match_profile(job), 0.5)

    assert score.evidence_score > 0.0
    assert any(reason.startswith(f"{field}:") for reason in _match_reasons(profile, job))
    assert _missing_requirements(profile, job) == []


@pytest.mark.parametrize(
    ("candidate", "job", "expected"),
    [
        (set(), {"python"}, 0.0),
        ({"python"}, set(), 0.0),
        ({"python", "sql"}, {"python", "cloud", "linux"}, 0.5),
    ],
)
def test_overlap_uses_candidate_terms_as_denominator(
    candidate: set[str], job: set[str], expected: float
) -> None:
    assert retrieval.overlap_score(candidate, job) == expected


def test_multiple_facts_and_skill_aliases_share_one_component() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed_fact("skills", "Python"),
            confirmed_fact("technical_skills", "SQL"),
            confirmed_fact("skills", "Python"),
        ]
    )
    job_profile = build_job_match_profile(
        Job(
            document_id="job",
            title="Python",
            description="Requirements: Python.",
        )
    )

    score = retrieval.score_job_evidence(profile, job_profile, 0.5)

    assert score.skill_score == 0.5
    assert score.evidence_score == 0.125


def test_final_score_tie_sorts_by_document_id() -> None:
    jobs = [
        build_job_match_profile(
            Job(
                document_id=document_id,
                title="Engineer",
                description="Responsibilities: Python.",
            )
        )
        for document_id in ("job-b", "job-a")
    ]
    profile = ProfileDraft(facts=[confirmed_fact("skills", "Python")])

    ranked = retrieval.rerank_scored_jobs(profile, [0.5, 0.5], jobs)

    assert [job.job.document_id for _, job in ranked] == ["job-a", "job-b"]


def test_reranking_does_not_round_before_sorting() -> None:
    jobs = [
        build_job_match_profile(
            Job(
                document_id=document_id,
                title="Engineer",
                description="Responsibilities: Python.",
            )
        )
        for document_id in ("job-a", "job-b")
    ]

    ranked = retrieval.rerank_scored_jobs(ProfileDraft(), [0.5, 0.50000001], jobs)

    assert [job.job.document_id for _, job in ranked] == ["job-b", "job-a"]
    assert ranked[0][0].final_score > ranked[1][0].final_score


def test_retrieval_reranks_all_nine_jobs_and_caches_structured_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = [
        Job(
            document_id=f"job-{index}",
            title="General Role",
            description="Responsibilities: Administration.",
        )
        for index in range(8)
    ]
    jobs.append(Job(document_id="job-9", title="RAG Engineer", description=RAG_DESCRIPTION))
    embedder = KeywordEmbedder()
    service = RetrievalService(jobs, embedder)
    profile = ProfileDraft(facts=[confirmed_fact("project", "embeddings and FAISS")])

    first = service.retrieve(profile, top_k=1)

    assert first[0].document_id == "job-9"
    assert first[0].score == first[0].score_breakdown.final_score == 0.18
    assert first[0].score_breakdown.project_score == 1.0
    assert first[0].match_reasons == ["project: embeddings, faiss"]
    assert len(embedder.calls[0]) == 9

    def reject_rebuild(job: Job) -> retrieval.JobMatchProfile:
        raise AssertionError("Structured job profiles should be cached")

    monkeypatch.setattr(retrieval, "build_job_match_profile", reject_rebuild)
    assert service.retrieve(profile, top_k=1) == first
    assert len(embedder.calls) == 3


def test_match_reasons_only_explain_scored_source_backed_components() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed_fact("project", "Python"),
            confirmed_fact("summary", "Python"),
            confirmed_fact("technical_skills", "SQL"),
        ]
    )
    job = Job(
        document_id="job",
        title="Engineer",
        description="Requirements: Python. Preferred qualifications: SQL.",
    )

    assert _match_reasons(profile, job) == []


def test_generic_project_and_role_words_are_not_specialisation_evidence() -> None:
    profile = ProfileDraft(facts=[confirmed_fact("project", "project role")])
    job = Job(document_id="job", title="Project Role", description="Responsibilities: Python.")

    score = retrieval.score_job_evidence(profile, build_job_match_profile(job), 0.5)

    assert score.project_score == 0.0
    assert _match_reasons(profile, job) == []


def test_job_repository_loads_the_nine_authoritative_unique_jobs() -> None:
    path = Path(__file__).parents[2] / "data" / "jobs.jsonl"

    jobs = JobRepository.load(path)

    assert len(jobs) == 9
    assert len({job.document_id for job in jobs}) == 9
    assert jobs[0].title == "Graduate AI Engineer"


def test_job_repository_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    row = {
        "document_id": "duplicate",
        "title": "Role",
        "description": "Description",
        "location": None,
        "job_type": None,
        "salary": None,
        "benefits": [],
    }
    path = tmp_path / "jobs.jsonl"
    path.write_text("\n".join([json.dumps(row), json.dumps(row)]), encoding="utf-8")

    with pytest.raises(JobDataError, match="unique"):
        JobRepository.load(path, expected_count=2)


def test_profile_query_is_deterministic_and_contains_only_confirmed_facts() -> None:
    profile = ProfileDraft(
        facts=[
            confirmed_fact("skills", "Python, REST APIs"),
            Fact(
                field="name",
                value="Unconfirmed Name",
                source=FactSource(
                    source_type=FactSourceType.USER_MESSAGE,
                    reference="message-2",
                ),
            ),
            confirmed_fact("target_role", "Backend Engineer"),
        ]
    )

    assert build_profile_query(profile) == (
        "target_role: Backend Engineer\nskills: Python, REST APIs"
    )


def test_job_match_profile_preserves_sections_and_source_spans() -> None:
    job = Job(
        document_id="rag",
        title="AI Engineer",
        description=(
            "About the role: Build applications. Responsibilities: Design RAG pipelines "
            "and AI-agent workflows. Requirements: Python; RAG. Preferred experience "
            "includes LangChain."
        ),
    )

    profile = build_job_match_profile(job)

    assert "rag" in profile.specialisation_terms
    assert profile.responsibility_spans == (
        "Design RAG pipelines and AI-agent workflows.",
    )
    assert profile.mandatory_requirement_spans == ("Python", "RAG")
    assert "LangChain" in profile.optional_requirement_spans[0]


def test_retrieval_result_requires_a_complete_score_breakdown() -> None:
    schema = RetrievalResult.model_json_schema()

    assert schema["properties"]["score_breakdown"]["$ref"].endswith(
        "RetrievalScoreBreakdown"
    )
    breakdown = schema["$defs"]["RetrievalScoreBreakdown"]
    expected_fields = {
        "semantic_score",
        "project_score",
        "skill_score",
        "target_role_score",
        "education_score",
        "experience_score",
        "evidence_score",
        "final_score",
    }
    assert set(breakdown["properties"]) == expected_fields
    assert set(breakdown["required"]) == expected_fields


def test_retrieval_returns_top_three_unique_jobs_with_exact_excerpts_and_cached_jobs() -> None:
    jobs = [
        Job(
            document_id="job-b",
            title="Python Engineer",
            description="Maintain Python services. Support the team.",
        ),
        Job(
            document_id="job-a",
            title="API Engineer",
            description=(
                "Build Python APIs. Requirements: Python; three years of cloud experience."
            ),
        ),
        Job(
            document_id="job-c",
            title="Vision Engineer",
            description="Build vision systems. Review datasets.",
        ),
        Job(
            document_id="job-d",
            title="Operations Analyst",
            description="Improve business processes.",
        ),
    ]
    embedder = KeywordEmbedder()
    service = RetrievalService(jobs, embedder)
    profile = ProfileDraft(
        facts=[
            confirmed_fact("skills", "Python and API development"),
            confirmed_fact("target_role", "Python API Engineer"),
        ]
    )

    first = service.retrieve(profile)
    second = service.retrieve(profile)

    assert [result.document_id for result in first] == ["job-a", "job-b", "job-c"]
    assert len({result.document_id for result in first}) == 3
    assert first[0].excerpt == "Build Python APIs."
    assert first[0].excerpt in jobs[1].description
    assert first[0].score == first[0].score_breakdown.final_score
    assert first[0].score_breakdown.semantic_score == 1.0
    assert first[0].score_breakdown.evidence_score > 0.0
    assert first[0].match_reasons
    assert first[0].matched_skills == ["Python"]
    assert first[0].missing_requirements == ["three years of cloud experience"]
    assert first[0].eligibility_notes == [
        "Relevance and evidence gaps do not decide eligibility; verify the full job record."
    ]
    assert first == second
    assert len(embedder.calls) == 3
    assert len(embedder.calls[0]) == 4
    assert len(embedder.calls[1]) == 1
    assert len(embedder.calls[2]) == 1


def test_retrieval_rejects_draft_profile_facts() -> None:
    service = RetrievalService(
        [Job(document_id="job-a", title="Role", description="Build Python APIs.")],
        KeywordEmbedder(),
    )
    profile = ProfileDraft(
        facts=[
            Fact(
                field="skills",
                value="Python",
                source=FactSource(
                    source_type=FactSourceType.USER_MESSAGE,
                    reference="message-1",
                ),
            )
        ]
    )

    with pytest.raises(ProfileNotConfirmedError):
        service.retrieve(profile)


def test_missing_requirements_does_not_treat_shared_generic_words_as_evidence() -> None:
    job = Job(
        document_id="senior-python",
        title="Senior Python Engineer",
        description=(
            "Requirements: Three years of professional Python experience; "
            "a master's degree in computer science; Python."
        ),
    )
    profile = ProfileDraft(
        facts=[
            confirmed_fact("education", "Bachelor of Computing Science"),
            confirmed_fact("skills", "Python"),
            confirmed_fact("experience", "Four years in retail customer service"),
        ]
    )

    missing = _missing_requirements(profile, job)

    assert "Three years of professional Python experience" in missing
    assert "a master's degree in computer science" in missing
    assert "Python" not in missing


def test_missing_requirements_ignores_aspirations_and_returns_every_gap() -> None:
    requirements = [
        "production cloud deployment",
        "Kubernetes",
        "Terraform",
        "streaming systems",
        "model monitoring",
        "incident response",
    ]
    job = Job(
        document_id="cloud-role",
        title="Cloud Engineer",
        description=f"Requirements: {'; '.join(requirements)}.",
    )
    profile = ProfileDraft(
        facts=[
            confirmed_fact(
                "summary",
                "Interested in cloud deployment but no production experience",
            ),
            confirmed_fact("target_role", "Cloud Engineer"),
        ]
    )

    assert _missing_requirements(profile, job) == requirements


def test_matched_skills_requires_the_complete_declared_skill() -> None:
    job = Job(
        document_id="data-role",
        title="Data Engineer",
        description="Build data pipelines with Python.",
    )
    profile = ProfileDraft(
        facts=[confirmed_fact("skills", "Python, data storytelling")]
    )

    assert _matched_skills(profile, job) == ["Python"]


def test_negative_or_aspirational_facts_are_not_presented_as_match_evidence() -> None:
    job = Job(
        document_id="python-role",
        title="Python Engineer",
        description="Build production Python services.",
    )
    profile = ProfileDraft(
        facts=[
            confirmed_fact("skills", "No Python experience"),
            confirmed_fact("project", "Currently learning production Python"),
        ]
    )

    assert _matched_skills(profile, job) == []
    assert _match_reasons(profile, job) == []


def test_conjunctive_requirement_reports_each_unconfirmed_term() -> None:
    job = Job(
        document_id="healthcare-role",
        title="Healthcare ML Engineer",
        description="Requirements: Python, SQL, and Linux.",
    )
    profile = ProfileDraft(
        facts=[confirmed_fact("skills", "Python, SQL")]
    )

    assert _missing_requirements(profile, job) == ["Python, SQL, and Linux"]


def test_alternative_requirement_does_not_pass_on_generic_data_overlap() -> None:
    job = Job(
        document_id="nlp-role",
        title="NLP Engineer",
        description=(
            "Requirements: big-data technologies such as Spark, Hadoop, Kafka, "
            "or vector databases."
        ),
    )
    generic_profile = ProfileDraft(
        facts=[confirmed_fact("skills", "data analysis")]
    )
    spark_profile = ProfileDraft(
        facts=[confirmed_fact("skills", "Apache Spark")]
    )

    assert _missing_requirements(generic_profile, job) == [
        "big-data technologies such as Spark, Hadoop, Kafka, or vector databases"
    ]
    assert _missing_requirements(spark_profile, job) == []


def test_up_to_years_is_treated_as_a_maximum_not_a_minimum() -> None:
    job = Job(
        document_id="graduate-role",
        title="Graduate Engineer",
        description="Requirements: up to two years of professional experience.",
    )
    early_career = ProfileDraft(
        facts=[confirmed_fact("experience", "One year of professional experience")]
    )
    above_maximum = ProfileDraft(
        facts=[confirmed_fact("experience", "Three years of professional experience")]
    )

    assert _missing_requirements(early_career, job) == []
    assert _missing_requirements(above_maximum, job) == [
        "up to two years of professional experience"
    ]


def test_compound_degree_requirement_keeps_the_additional_skill_gap() -> None:
    jobs = JobRepository.load(JobRepository.default_data_path())
    job = next(
        job for job in jobs if job.document_id == "recommendation_systems_ml_engineer"
    )
    profile = ProfileDraft(
        facts=[confirmed_fact("education", "Bachelor of Computing Science")]
    )

    missing = _missing_requirements(profile, job)

    assert any("problem-solving" in requirement for requirement in missing)


def test_requirement_parser_handles_requirements_and_minimum_qualifications() -> None:
    jobs = JobRepository.load(JobRepository.default_data_path())
    by_id = {job.document_id: job for job in jobs}

    graduate = _requirement_items(by_id["graduate_ai_engineer"].description)
    trust_safety = _requirement_items(by_id["trust_safety_ml_engineer"].description)

    assert graduate[0].startswith("A degree in artificial intelligence")
    assert trust_safety[0].startswith("A bachelor's degree")


@pytest.mark.parametrize(
    ("document_id", "optional_example"),
    [
        ("computer_vision_engineer", "YOLO"),
        ("trust_safety_ml_engineer", "Experience applying machine learning"),
        ("healthcare_ml_engineer", "MLOps"),
        ("rag_agent_engineer", "LangChain"),
    ],
)
def test_requirement_parser_excludes_optional_sections(
    document_id: str, optional_example: str
) -> None:
    jobs = JobRepository.load(JobRepository.default_data_path())
    by_id = {job.document_id: job for job in jobs}

    mandatory_requirements = _requirement_items(by_id[document_id].description)

    assert mandatory_requirements
    assert all(optional_example not in item for item in mandatory_requirements)
