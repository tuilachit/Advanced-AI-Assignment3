"""Prepare isolated feedback inputs and validate synchronous untrusted assessments.

Lock policy: never call flow methods or a provider while holding a feedback lock.
Preparation owns no shared mutable state and needs no feedback lock. Completed
interviews are immutable through the flow API; bracketed reads verify that premise.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.domain.feedback_models import (
    Applicability,
    CriterionFeedback,
    CriterionName,
    FeedbackRequest,
    ModelFeedbackAssessment,
    ModelQuestionAssessment,
)
from app.domain.interview_models import Interview, InterviewContextSnapshot, TranscriptTurn
from app.domain.models import FactStatus
from app.providers.base import ProviderProtocolError
from app.providers.interview_feedback import (
    FeedbackAssessmentInput,
    FeedbackContextInput,
    FinalCandidateAnswerInput,
    InterviewFeedbackProvider,
    QuestionAssessmentInput,
)
from app.services.interview_flow import InterviewConflictError, InterviewFlowService

# Fact.field is unrestricted. These exact labels come from workflow required fields,
# retrieval's technical_skills alias and profile_to_confirmed_facts fixtures. Unknown
# labels (including contact/account/link fields) are excluded by default. Do not send
# names, fact IDs, source references, CVs or unrestricted resume-entry display text.
# This is field minimisation, not a detector for identifiers embedded in allowed prose;
# submitted answer text remains exact evidence and is never rewritten here.
_CONTEXT_FIELDS = frozenset({
    "education", "skills", "technical_skills", "project", "experience", "target_role",
})
_INVALID_ASSESSMENT = "The feedback assessment did not satisfy the evidence contract."


class _AssessmentContractError(ValueError):
    """An explicit violation of the assessment contract by a provider proposal."""


def _candidate_context(context: InterviewContextSnapshot) -> tuple[str, ...]:
    return tuple(
        f"{fact.field}: {fact.value}" for fact in context.confirmed_facts
        if fact.field in _CONTEXT_FIELDS and fact.status == FactStatus.CONFIRMED
    )


@dataclass(frozen=True, slots=True)
class PreparedFeedback:
    """Caller-owned copies; empty answers remain available for local insufficient evidence.

    All non-planned questions are retained here. Only answered questions with usable
    submitted turns go to the provider. Assessment synthesizes all five
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

        assessment_input = FeedbackAssessmentInput(
            context=FeedbackContextInput(
                context.job.title, context.job.description, _candidate_context(context)
            ),
            questions=tuple(question for question in asked if question.answers),
        )
        return PreparedFeedback(
            request=request, interview=interview, context=context,
            submitted_turn_ids=submitted, asked_questions=tuple(asked),
            answer_turns=tuple(answer_turns), assessment_input=assessment_input,
        )

    def assess(self, prepared: PreparedFeedback) -> ModelFeedbackAssessment:
        """Return validated criteria in canonical order, without publishing a report.

        No shared state or locks are used. Category is the structured applicability
        authority: behavioural -> STAR, technical -> technical reasoning. There is
        no structured past-experience flag for the technical STAR exception, so we
        conservatively disallow it rather than infer it from wording.
        """
        # Detach mutable Pydantic snapshots before invoking external code.
        interview = prepared.interview.model_copy(deep=True)
        turns = {turn.turn_id: turn.model_copy(deep=True) for turn in prepared.answer_turns}
        submitted = prepared.submitted_turn_ids
        inputs = prepared.assessment_input
        proposal = self._provider.assess(inputs) if inputs.questions else ModelFeedbackAssessment(
            questions=[]
        )
        try:
            # Revalidate even injected providers' mutated/model_construct objects.
            validated = ModelFeedbackAssessment.model_validate(proposal.model_dump(warnings=False))
            expected = {question.question_id: question for question in inputs.questions}
            if {question.question_id for question in validated.questions} != set(expected):
                raise _AssessmentContractError("question coverage")
            canonical = {question.question_id: question for question in interview.questions}
            for question in validated.questions:
                source = expected[question.question_id]
                if {item.criterion for item in question.criteria} != set(CriterionName):
                    raise _AssessmentContractError("criterion coverage")
                allowed = {answer.turn_id: answer.text for answer in source.answers}
                category = canonical[question.question_id].category
                for item in question.criteria:
                    inapplicable = (
                        item.criterion == CriterionName.STAR and category == "technical"
                    ) or (
                        item.criterion == CriterionName.TECHNICAL_REASONING
                        and category == "behavioural"
                    )
                    if inapplicable != (item.applicability == Applicability.NOT_APPLICABLE):
                        raise _AssessmentContractError("applicability")
                    if item.applicability != Applicability.ASSESSED and item.evidence:
                        raise _AssessmentContractError("non-assessed evidence")
                    for evidence in item.evidence:
                        turn = turns.get(evidence.turn_id)
                        if (
                            evidence.turn_id not in allowed
                            or evidence.turn_id not in submitted
                            or turn is None
                            or turn.speaker != "candidate"
                            or turn.transcript_status != "final"
                            or turn.question_id != question.question_id
                            or turn.text != allowed[evidence.turn_id]
                            or evidence.quote not in turn.text
                        ):
                            raise _AssessmentContractError("evidence provenance")
            by_id = {question.question_id: question for question in validated.questions}
            combined: list[ModelQuestionAssessment] = []
            for canonical_question in interview.questions:
                if canonical_question.status == "planned":
                    continue
                if canonical_question.question_id in by_id:
                    if canonical_question.status != "answered":
                        raise _AssessmentContractError("unanswered assessment")
                    combined.append(by_id[canonical_question.question_id])
                else:
                    explanation = (
                        "This question was skipped; no submitted answer is assessed."
                        if canonical_question.status == "skipped" else
                        "No usable submitted final candidate answer is available for this question."
                    )
                    combined.append(ModelQuestionAssessment(
                        question_id=canonical_question.question_id,
                        criteria=[CriterionFeedback(
                            criterion=criterion,
                            applicability=Applicability.INSUFFICIENT_EVIDENCE,
                            score=None, evidence=[], explanation=explanation,
                        ) for criterion in CriterionName],
                    ))
            return ModelFeedbackAssessment(questions=combined)
        except (ValidationError, _AssessmentContractError):
            raise ProviderProtocolError(_INVALID_ASSESSMENT) from None
