"""Pydantic models for the A3 mock-interview flow (Interface Contract v1, sections 3-6, 9).

These models are the source of truth for the interview wire format. The frontend types are
generated from the FastAPI OpenAPI schema; do not hand-write a second copy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.domain.models import CVDocument, Fact, ResumeEntry, StrictModel

InterviewPhase = Literal["ready", "active", "finalizing", "completed", "cancelled", "failed"]
FeedbackStatus = Literal["not_requested", "generating", "ready", "failed"]
QuestionCategory = Literal["behavioural", "technical"]
QuestionKind = Literal["main", "follow_up"]
QuestionStatus = Literal["planned", "issued", "answered", "skipped"]
EndReason = Literal[
    "user_finished", "time_limit", "questions_complete", "user_cancelled", "provider_failure"
]

RequestId = Annotated[str, Field(min_length=1, max_length=200)]
OpaqueId = Annotated[str, Field(min_length=1, max_length=200)]

PASTED_TITLE_MAX = 200
PASTED_DESCRIPTION_MAX = 20_000
QUESTION_TEXT_MAX = 500
RATIONALE_MAX = 1_000


def _stripped(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


# ---------------------------------------------------------------------------
# Creation request (section 3)
# ---------------------------------------------------------------------------


class SuppliedJobRequest(StrictModel):
    source: Literal["supplied_job"]
    document_id: OpaqueId


class PastedJobRequest(StrictModel):
    source: Literal["pasted_job"]
    title: str = Field(min_length=1, max_length=PASTED_TITLE_MAX)
    description: str = Field(min_length=1, max_length=PASTED_DESCRIPTION_MAX)

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return _stripped(value)


InterviewJobRequest = Annotated[
    SuppliedJobRequest | PastedJobRequest, Field(discriminator="source")
]


class InterviewConfig(StrictModel):
    interview_type: Literal["behavioural", "technical", "mixed"] = "mixed"
    duration_minutes: Literal[5, 10, 15] = 10
    main_question_count: int = Field(default=4, ge=3, le=6)
    max_follow_ups_per_question: int = Field(default=1, ge=0, le=2)
    language: Literal["en"] = "en"


class InterviewConsent(StrictModel):
    send_audio_to_provider: bool
    retain_transcript_for_feedback: bool


class CreateInterviewRequest(StrictModel):
    request_id: RequestId
    cv_id: OpaqueId | None = None
    job: InterviewJobRequest
    config: InterviewConfig = Field(default_factory=InterviewConfig)
    consent: InterviewConsent


# ---------------------------------------------------------------------------
# Interview records (section 4)
# ---------------------------------------------------------------------------


class InterviewJob(StrictModel):
    source: Literal["supplied_job", "pasted_job"]
    document_id: str | None
    title: str
    description: str


class InterviewQuestion(StrictModel):
    question_id: str
    parent_question_id: str | None
    kind: QuestionKind
    category: QuestionCategory
    status: QuestionStatus
    text: str
    rationale: str
    fact_ids: list[str]
    resume_entry_ids: list[str]
    job_requirement_excerpt: str | None


class TranscriptTiming(StrictModel):
    clock_id: str = Field(min_length=1, max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    source: Literal["provider_vad", "recording"]

    @model_validator(mode="after")
    def ordered(self) -> TranscriptTiming:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not be earlier than start_ms")
        return self


class TranscriptTurn(StrictModel):
    turn_id: OpaqueId
    question_id: OpaqueId
    speaker: Literal["interviewer", "candidate"]
    input_mode: Literal["live_voice", "recorded_audio"]
    transcript_version: int = Field(ge=1)
    transcript_status: Literal["pending", "partial", "final", "failed"]
    text: str = Field(max_length=20_000)
    delivery_status: Literal["complete", "interrupted", "unknown", "not_applicable"]
    timing: TranscriptTiming | None

    @model_validator(mode="after")
    def delivery_matches_speaker(self) -> TranscriptTurn:
        if self.speaker == "candidate" and self.delivery_status != "not_applicable":
            raise ValueError("candidate turns must use delivery_status not_applicable")
        if self.speaker == "interviewer" and self.delivery_status == "not_applicable":
            raise ValueError("interviewer turns must describe playback delivery")
        return self


class Interview(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    interview_id: str
    phase: InterviewPhase
    flow_revision: int
    transcript_revision: int
    context_hash: str
    profile_revision: int
    resume_entries_revision: int
    cv_id: str | None
    cv_content_hash: str | None
    job: InterviewJob
    config: InterviewConfig
    questions: list[InterviewQuestion]
    current_question_id: str | None
    turns: list[TranscriptTurn]
    feedback_status: FeedbackStatus
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    end_reason: EndReason | None


class InterviewContextSnapshot(StrictModel):
    """Frozen copy of everything the interview is allowed to use (never sent to the browser)."""

    confirmed_facts: list[Fact]
    approved_entries: list[ResumeEntry]
    cv: CVDocument | None
    job: InterviewJob
    config: InterviewConfig


# ---------------------------------------------------------------------------
# Question planning (internal planner output, validated by the flow service)
# ---------------------------------------------------------------------------


class PlannedQuestion(StrictModel):
    category: QuestionCategory
    text: str = Field(min_length=1, max_length=QUESTION_TEXT_MAX)
    rationale: str = Field(min_length=1, max_length=RATIONALE_MAX)
    fact_ids: list[str] = Field(default_factory=list)
    resume_entry_ids: list[str] = Field(default_factory=list)
    job_requirement_excerpt: str | None = None


class QuestionPlanProposal(StrictModel):
    questions: list[PlannedQuestion]


# ---------------------------------------------------------------------------
# Progression (section 5) and lifecycle controls (section 9)
# ---------------------------------------------------------------------------


class FollowUpProposal(StrictModel):
    text: str = Field(min_length=1, max_length=QUESTION_TEXT_MAX)
    rationale: str = Field(min_length=1, max_length=RATIONALE_MAX)

    @field_validator("text", "rationale")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return _stripped(value)


class AskQuestionStep(StrictModel):
    action: Literal["ask_question"]
    question: InterviewQuestion
    flow_revision: int


class FinishStep(StrictModel):
    action: Literal["finish"]
    reason: Literal["time_limit", "questions_complete"]
    flow_revision: int


NextStep = Annotated[AskQuestionStep | FinishStep, Field(discriminator="action")]


class StartInterviewRequest(StrictModel):
    request_id: RequestId
    expected_flow_revision: int = Field(ge=0)
    connection_id: OpaqueId | None = None


class StartInterviewResponse(StrictModel):
    interview: Interview
    next_step: NextStep


class NextStepRequest(StrictModel):
    request_id: RequestId
    expected_flow_revision: int = Field(ge=0)
    answered_question_id: OpaqueId
    answer_turn_ids: list[OpaqueId] = Field(min_length=1, max_length=50)
    follow_up_proposal: FollowUpProposal | None = None
    connection_id: OpaqueId | None = None


class SkipQuestionRequest(StrictModel):
    request_id: RequestId
    expected_flow_revision: int = Field(ge=0)
    question_id: OpaqueId
    connection_id: OpaqueId | None = None


class InterviewControlRequest(StrictModel):
    request_id: RequestId
    expected_flow_revision: int = Field(ge=0)
    connection_id: OpaqueId | None = None


# ---------------------------------------------------------------------------
# Transcript events (section 6)
# ---------------------------------------------------------------------------


class TurnEventRequest(StrictModel):
    event_id: OpaqueId
    connection_id: OpaqueId
    previous_turn_id: OpaqueId | None
    turn: TranscriptTurn


class TurnEventAck(StrictModel):
    event_id: str
    turn_id: str
    transcript_revision: int
