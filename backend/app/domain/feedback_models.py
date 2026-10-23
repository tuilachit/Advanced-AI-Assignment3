from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, AwareDatetime, Field, field_validator, model_validator

from app.domain.models import StrictModel


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankText = Annotated[str, AfterValidator(_not_blank)]


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class CriterionName(StrEnum):
    RELEVANCE = "relevance"
    SPECIFICITY = "specificity"
    STRUCTURE = "structure"
    TECHNICAL_REASONING = "technical_reasoning"
    STAR = "star"


class Applicability(StrEnum):
    ASSESSED = "assessed"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceQuote(StrictModel):
    turn_id: NonBlankText = Field(min_length=1)
    quote: NonBlankText = Field(min_length=1, max_length=1000)


class CriterionFeedback(StrictModel):
    criterion: CriterionName
    applicability: Applicability
    score: int | None = Field(default=None, ge=0, le=4, strict=True)
    explanation: NonBlankText = Field(min_length=1, max_length=1500)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    improvement: NonBlankText | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        if self.applicability is Applicability.ASSESSED:
            if self.score is None:
                raise ValueError("An assessed criterion requires a score.")

            if not self.evidence:
                raise ValueError("An assessed criterion requires transcript evidence.")

        elif self.score is not None:
            raise ValueError("A non-assessed criterion must have a null score.")

        return self


class SpeakingMetric(StrictModel):
    name: Literal[
        "words_per_minute",
        "transcript_filler_count",
        "pause_count",
    ]
    status: Literal["available", "not_available"]
    value: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)
    unit: Literal["words/min", "count"]
    method: NonBlankText = Field(min_length=1)
    unavailable_reason: NonBlankText | None = None
    turn_ids: list[NonBlankText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        expected_unit = "words/min" if self.name == "words_per_minute" else "count"
        if self.unit != expected_unit:
            raise ValueError("metric unit does not match its name")
        if self.unit == "count" and self.value is not None and not self.value.is_integer():
            raise ValueError("count metrics require whole-number values")
        _unique(self.turn_ids, "metric turn IDs")
        if self.status == "available":
            if self.value is None:
                raise ValueError("An available metric requires a value.")

            if self.unavailable_reason is not None:
                raise ValueError("An available metric cannot have an unavailable reason.")

        else:
            if self.value is not None:
                raise ValueError("An unavailable metric must have a null value.")

            if not self.unavailable_reason:
                raise ValueError("An unavailable metric requires an explanation.")

        return self


class QuestionFeedback(StrictModel):
    question_id: NonBlankText = Field(min_length=1)
    criteria: list[CriterionFeedback]
    speaking_metrics: list[SpeakingMetric]

    @model_validator(mode="after")
    def validate_uniqueness(self) -> Self:
        _unique([item.criterion for item in self.criteria], "criteria")
        _unique([item.name for item in self.speaking_metrics], "metrics")
        return self


class FeedbackReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: NonBlankText = Field(min_length=1)
    interview_id: NonBlankText = Field(min_length=1)
    context_hash: NonBlankText = Field(min_length=1)
    transcript_revision: int = Field(ge=0, strict=True)
    rubric_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    question_feedback: list[QuestionFeedback]
    limitations: list[NonBlankText] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_uniqueness(self) -> Self:
        _unique([item.question_id for item in self.question_feedback], "question IDs")
        return self


class ModelQuestionAssessment(StrictModel):
    question_id: NonBlankText = Field(min_length=1)
    criteria: list[CriterionFeedback]

    @model_validator(mode="after")
    def validate_uniqueness(self) -> Self:
        _unique([item.criterion for item in self.criteria], "criteria")
        return self


class ModelFeedbackAssessment(StrictModel):
    questions: list[ModelQuestionAssessment]

    @model_validator(mode="after")
    def validate_uniqueness(self) -> Self:
        _unique([item.question_id for item in self.questions], "question IDs")
        return self


class FeedbackRequest(StrictModel):
    request_id: NonBlankText = Field(min_length=1, max_length=200)
    expected_transcript_revision: int = Field(ge=0, strict=True)


class FeedbackStartResponse(StrictModel):
    feedback_status: Literal["generating"]
