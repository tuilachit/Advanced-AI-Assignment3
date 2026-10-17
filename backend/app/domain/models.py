from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )


class SessionState(StrEnum):
    COLLECTING_PROFILE = "collecting_profile"
    PROFILE_REVIEW = "profile_review"
    PROFILE_CONFIRMED = "profile_confirmed"
    RESUME_ENTRIES_REVIEW = "resume_entries_review"
    RESUME_ENTRIES_APPROVED = "resume_entries_approved"
    JOBS_RETRIEVED = "jobs_retrieved"
    JOB_SELECTED = "job_selected"
    CV_DRAFT = "cv_draft"
    CV_VALIDATED = "cv_validated"
    PDF_EXPORTED = "pdf_exported"


class FactStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class FactSourceType(StrEnum):
    USER_MESSAGE = "user_message"
    MANUAL_EDIT = "manual_edit"
    IMPORTED_TEST_PROFILE = "imported_test_profile"


class FactSource(StrictModel):
    source_type: FactSourceType
    reference: str


class FactInput(StrictModel):
    field: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=4000)

    @field_validator("field", "value")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class Fact(FactInput):
    fact_id: str = Field(default_factory=lambda: f"fact-{uuid4()}")
    status: FactStatus = FactStatus.DRAFT
    source: FactSource


class ProfileDraft(StrictModel):
    facts: list[Fact] = Field(default_factory=list)
    revision: int = 0


class Job(StrictModel):
    document_id: str
    title: str
    description: str
    location: str | None = None
    job_type: str | None = None
    salary: str | None = None
    benefits: list[str] = Field(default_factory=list)


class RetrievalScoreBreakdown(StrictModel):
    semantic_score: float = Field(ge=0.0, le=1.0)
    project_score: float = Field(ge=0.0, le=1.0)
    skill_score: float = Field(ge=0.0, le=1.0)
    target_role_score: float = Field(ge=0.0, le=1.0)
    education_score: float = Field(ge=0.0, le=1.0)
    experience_score: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class RetrievalResult(StrictModel):
    document_id: str
    title: str
    score: float = Field(description="Relevance score used to rank this job match.")
    score_breakdown: RetrievalScoreBreakdown
    excerpt: str
    match_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    eligibility_notes: list[str] = Field(default_factory=list)


class CVClaim(StrictModel):
    claim_id: str = Field(default_factory=lambda: f"claim-{uuid4()}")
    text: str
    fact_ids: list[str]
    verified: bool = False


class CVSection(StrictModel):
    heading: str
    claims: list[CVClaim] = Field(default_factory=list)


class CVDocument(StrictModel):
    cv_id: str = Field(default_factory=lambda: f"cv-{uuid4()}")
    target_job_id: str
    headline: str
    headline_fact_ids: list[str] = Field(default_factory=list)
    claims: list[CVClaim] = Field(default_factory=list)
    sections: list[CVSection] = Field(default_factory=list)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(StrictModel):
    issue_id: str = Field(default_factory=lambda: f"issue-{uuid4()}")
    claim_id: str | None = None
    severity: ValidationSeverity = ValidationSeverity.ERROR
    code: str
    message: str


class ResumeEntryKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"
    EDUCATION = "education"
    SKILLS = "skills"
    ACHIEVEMENT = "achievement"


class ResumeEntryStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"


class ResumeText(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    fact_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("fact_ids")
    @classmethod
    def validate_fact_ids(cls, value: list[str]) -> list[str]:
        if any(not fact_id.strip() for fact_id in value):
            raise ValueError("fact IDs must not be blank")
        return value


class ResumeEntryDetail(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    value: ResumeText

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ResumeEntry(StrictModel):
    entry_id: str = Field(default_factory=lambda: f"resume-entry-{uuid4()}")
    kind: ResumeEntryKind
    heading: ResumeText
    organisation_or_context: ResumeText | None = None
    details: list[ResumeEntryDetail] = Field(default_factory=list)
    bullets: list[ResumeText] = Field(default_factory=list, max_length=3)
    source_fact_ids: list[str] = Field(min_length=1)
    status: ResumeEntryStatus = ResumeEntryStatus.PROPOSED

    @field_validator("source_fact_ids")
    @classmethod
    def validate_source_fact_ids(cls, value: list[str]) -> list[str]:
        if any(not fact_id.strip() for fact_id in value):
            raise ValueError("source fact IDs must not be blank")
        return value

    @model_validator(mode="after")
    def validate_source_fact_union(self) -> ResumeEntry:
        nested_text = [self.heading, *self.bullets]
        if self.organisation_or_context is not None:
            nested_text.append(self.organisation_or_context)
        nested_text.extend(detail.value for detail in self.details)
        expected_fact_ids = list(
            dict.fromkeys(
                fact_id for text in nested_text for fact_id in text.fact_ids
            )
        )
        if self.source_fact_ids != expected_fact_ids:
            raise ValueError(
                "source_fact_ids must equal the de-duplicated union of nested fact_ids"
            )
        return self


class ResumeEntryEdit(StrictModel):
    heading: str = Field(min_length=1, max_length=1000)
    organisation_or_context: str | None = Field(default=None, max_length=1000)
    details: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("heading", "organisation_or_context")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("details", "bullets")
    @classmethod
    def strip_text_items(cls, values: list[str]) -> list[str]:
        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("must not contain blank text")
        return cleaned_values


class ResumeEntryValidationIssue(StrictModel):
    issue_id: str = Field(default_factory=lambda: f"resume-entry-issue-{uuid4()}")
    entry_id: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    code: str
    message: str


class AgentAction(StrictModel):
    action: Literal["ask", "update_profile", "retrieve_jobs", "generate_cv", "respond"]
    message: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentObservation(StrictModel):
    action: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class TraceEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: f"event-{uuid4()}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class Session(StrictModel):
    session_id: str
    state: SessionState = SessionState.COLLECTING_PROFILE
    profile: ProfileDraft = Field(default_factory=ProfileDraft)
    resume_entries: list[ResumeEntry] = Field(default_factory=list)
    resume_entries_revision: int = 0
    resume_entry_validation_issues: list[ResumeEntryValidationIssue] = Field(
        default_factory=list
    )
    retrieval_results: list[RetrievalResult] = Field(default_factory=list)
    selected_job_id: str | None = None
    cv: CVDocument | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    validated_content_hash: str | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
