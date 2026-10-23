"""Stage 4A: prepare isolated feedback inputs; no provider calls or publication yet.

Lock policy: never call flow methods or a provider while holding a feedback lock.
Preparation owns no shared mutable state and needs no feedback lock. Completed
interviews are immutable through the flow API; bracketed reads verify that premise.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.feedback_models import FeedbackRequest
from app.domain.interview_models import Interview, InterviewContextSnapshot, TranscriptTurn
from app.providers.interview_feedback import (
    FeedbackAssessmentInput,
    FeedbackContextInput,
    FinalCandidateAnswerInput,
    InterviewFeedbackProvider,
    QuestionAssessmentInput,
)
from app.services.interview_flow import InterviewConflictError, InterviewFlowService


@dataclass(frozen=True, slots=True)
class PreparedFeedback:
    """Caller-owned copies; empty answers remain available for local insufficient evidence.

    All non-planned questions are retained here. Only answered questions with usable
    submitted turns go to the provider. Later stages must synthesize all five
    insufficient-evidence criteria for the others, without consulting the provider.
    """

    request: FeedbackRequest
    interview: Interview
    context: InterviewContextSnapshot
    submitted_turn_ids: frozenset[str]
    asked_questions: tuple[QuestionAssessmentInput, ...]
    answer_turns: tuple[TranscriptTurn, ...]
    assessment_input: FeedbackAssessmentInput


def _evaluation_state(interview: Interview) -> dict[str, object]:
    return interview.model_dump(exclude={"feedback_status"})


class InterviewFeedbackService:
    def __init__(
        self, flow: InterviewFlowService, provider: InterviewFeedbackProvider
    ) -> None:
        self._flow = flow
        self._provider = provider

    def prepare(
        self, session_id: str, interview_id: str, request: FeedbackRequest
    ) -> PreparedFeedback:
        """Validate and project one stable completed attempt, without changing state."""
        request = FeedbackRequest.model_validate(request.model_dump())
        interview = self._flow.get(session_id, interview_id)
        if interview.phase != "completed":
            raise InterviewConflictError(
                "invalid_interview_phase", "Feedback requires a completed interview.",
                {"phase": interview.phase},
            )
        if interview.transcript_revision != request.expected_transcript_revision:
            raise InterviewConflictError(
                "transcript_revision_conflict", "The transcript changed. Reload and retry.",
                {"transcript_revision": interview.transcript_revision},
            )
        context = self._flow.get_context(session_id, interview_id)
        submitted = frozenset(self._flow.submitted_turn_ids(session_id, interview_id))
        latest = self._flow.get(session_id, interview_id)
        latest_submitted = self._flow.submitted_turn_ids(session_id, interview_id)
        if (
            _evaluation_state(interview) != _evaluation_state(latest)
            or submitted != latest_submitted
        ):
            raise InterviewConflictError(
                "feedback_snapshot_conflict", "The interview changed. Reload and retry."
            )

        asked: list[QuestionAssessmentInput] = []
        answer_turns: list[TranscriptTurn] = []
        for question in interview.questions:
            if question.status == "planned":
                continue
            # Status is authoritative. An interviewer transcript is not required.
            turns = [
                turn for turn in interview.turns
                if question.status == "answered"
                and turn.question_id == question.question_id
                and turn.turn_id in submitted
                and turn.speaker == "candidate"
                and turn.transcript_status == "final"
                and turn.text.strip()
            ]
            answer_turns.extend(turns)
            asked.append(QuestionAssessmentInput(
                question_id=question.question_id, text=question.text,
                category=question.category,
                answers=tuple(FinalCandidateAnswerInput(turn.turn_id, turn.text) for turn in turns),
            ))

        candidate_context = [f"{fact.field}: {fact.value}" for fact in context.confirmed_facts]
        for entry in context.approved_entries:
            candidate_context.append(entry.heading.text)
            if entry.organisation_or_context is not None:
                candidate_context.append(entry.organisation_or_context.text)
            candidate_context.extend(
                f"{detail.label}: {detail.value.text}" for detail in entry.details
            )
            candidate_context.extend(bullet.text for bullet in entry.bullets)
        assessment_input = FeedbackAssessmentInput(
            context=FeedbackContextInput(
                context.job.title, context.job.description, tuple(candidate_context)
            ),
            questions=tuple(question for question in asked if question.answers),
        )
        return PreparedFeedback(
            request=request, interview=interview, context=context,
            submitted_turn_ids=submitted, asked_questions=tuple(asked),
            answer_turns=tuple(answer_turns), assessment_input=assessment_input,
        )
