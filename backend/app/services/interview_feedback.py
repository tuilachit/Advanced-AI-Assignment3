"""Prepare isolated feedback inputs and validate synchronous untrusted assessments.

Lock policy: never call flow methods or a provider while holding a feedback lock.
Preparation owns no shared mutable state and needs no feedback lock. Completed
interviews are immutable through the flow API; bracketed reads verify that premise.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import ValidationError

from app.domain.feedback_models import (
    Applicability,
    CriterionFeedback,
    CriterionName,
    FeedbackReport,
    FeedbackRequest,
    FeedbackStartResponse,
    ModelFeedbackAssessment,
    ModelQuestionAssessment,
    QuestionFeedback,
)
from app.domain.interview_models import Interview, InterviewContextSnapshot, TranscriptTurn
from app.domain.models import FactStatus
from app.providers.base import ProviderProtocolError, ProviderUnavailableError
from app.providers.interview_feedback import (
    FeedbackAssessmentInput,
    FeedbackContextInput,
    FinalCandidateAnswerInput,
    InterviewFeedbackProvider,
    QuestionAssessmentInput,
)
from app.services.feedback_metrics import calculate_speaking_metrics, count_words
from app.services.interview_flow import InterviewConflictError, InterviewError, InterviewFlowService

# Fact.field is unrestricted. These exact labels come from workflow required fields,
# retrieval's technical_skills alias and profile_to_confirmed_facts fixtures. Unknown
# labels (including contact/account/link fields) are excluded by default. Do not send
# names, fact IDs, source references, CVs or unrestricted resume-entry display text.
# This is field minimisation, not a detector for identifiers embedded in allowed prose;
# submitted answer text remains exact evidence and is never rewritten here.
_CONTEXT_FIELDS = frozenset(
    {
        "education",
        "skills",
        "technical_skills",
        "project",
        "experience",
        "target_role",
    }
)
_INVALID_ASSESSMENT = "The feedback assessment did not satisfy the evidence contract."


class _AssessmentContractError(ValueError):
    """An explicit violation of the assessment contract by a provider proposal."""


def _candidate_context(context: InterviewContextSnapshot) -> tuple[str, ...]:
    return tuple(
        f"{fact.field}: {fact.value}"
        for fact in context.confirmed_facts
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


class FeedbackJobRunner(Protocol):
    """Return after accepting once; raise only if not accepted. May execute inline."""

    def submit(self, job: Callable[[], None]) -> None: ...


@dataclass(frozen=True, slots=True)
class FeedbackFailure:
    code: str
    message: str
    retryable: bool = True


@dataclass(frozen=True, slots=True)
class FeedbackResult:
    feedback_status: Literal["not_requested", "generating", "ready", "failed"]
    report: FeedbackReport | None = None
    error: FeedbackFailure | None = None


class FeedbackAdmissionError(InterviewError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__(
            "feedback_status_update_failed",
            "Feedback could not be started. Please retry.",
            {"retryable": True},
        )


_STATUS_FAILURE = FeedbackFailure(
    "feedback_status_update_failed", "Feedback status could not be updated. Please retry."
)
_EvaluationKey = tuple[str, str, str, int, str, str]


@dataclass(frozen=True, slots=True)
class _RequestBinding:
    fingerprint: str
    evaluation_key: _EvaluationKey


@dataclass(slots=True)
class _Attempt:
    """All mutable fields are private and protected by the feedback lock.

    Each attempt exclusively owns status writes until finished. Retry admission
    waits for cleanup, so status writes from different attempts never overlap.
    Events are signalled only after their outcome fields have been set.
    """

    token: int
    key: _EvaluationKey
    initial_done: Event
    finished: Event
    phase: Literal["admitting", "queued", "running", "terminal", "finished"] = "admitting"
    claimed: bool = False
    initial_failed: bool = False
    status: Literal["generating", "ready", "failed"] = "generating"
    report_json: bytes | None = None
    error: FeedbackFailure | None = None


def _evaluation_key(prepared: PreparedFeedback) -> _EvaluationKey:
    payload = {
        "interview": prepared.interview.model_dump(mode="json", exclude={"feedback_status"}),
        "context": prepared.context.model_dump(mode="json"),
        "submitted_turn_ids": sorted(prepared.submitted_turn_ids),
        "policy_version": "1.0",
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    interview = prepared.interview
    return (
        interview.session_id,
        interview.interview_id,
        interview.context_hash,
        interview.transcript_revision,
        "1.0",
        digest,
    )


class InterviewFeedbackService:
    def __init__(
        self,
        flow: InterviewFlowService,
        provider: InterviewFeedbackProvider,
        *,
        clock: Callable[[], datetime] | None = None,
        report_id_factory: Callable[[], str] | None = None,
        runner: FeedbackJobRunner | None = None,
    ) -> None:
        self._flow = flow
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._report_id_factory = report_id_factory or (lambda: str(uuid4()))
        self._runner = runner
        self._feedback_lock = Lock()
        self._requests: dict[tuple[str, str, str], _RequestBinding] = {}
        self._evaluations: dict[_EvaluationKey, _Attempt] = {}
        self._current: dict[tuple[str, str], _Attempt] = {}
        self._next_token = 0

    def start(
        self, session_id: str, interview_id: str, request: FeedbackRequest
    ) -> FeedbackStartResponse:
        """Admit/reuse work; a POST observing failed work explicitly retries it."""
        request = FeedbackRequest.model_validate(request.model_dump())
        self._flow.get(session_id, interview_id)  # ownership before cache lookup
        resource = (session_id, interview_id)
        request_key = (*resource, request.request_id)
        fingerprint = request.model_dump_json()
        with self._feedback_lock:
            binding = self._requests.get(request_key)
            if binding is not None and binding.fingerprint != fingerprint:
                raise InterviewConflictError("request_id_conflict", "Request input has changed.")
            observed = self._current.get(resource)
            observed_failed = (
                observed is not None
                and observed.status == "failed"
                and observed.phase == "finished"
            )
        prepared = self.prepare(session_id, interview_id, request)
        key = _evaluation_key(prepared)
        while True:
            wait_for: Event | None = None
            with self._feedback_lock:
                binding = self._requests.get(request_key)
                if binding is not None and (
                    binding.fingerprint != fingerprint or binding.evaluation_key != key
                ):
                    raise InterviewConflictError(
                        "request_id_conflict", "Request input or its evaluation has changed."
                    )
                current = self._current.get(resource)
                if current is not None and current.phase == "terminal":
                    wait_for = current.finished
                elif current is not None and current.key != key and current.status == "generating":
                    raise InterviewConflictError(
                        "feedback_state_changed", "Another feedback evaluation is still finishing."
                    )
                else:
                    attempt = self._evaluations.get(key)
                    # A concurrent POST that observed the old attempt must reuse
                    # its replacement even if that replacement failed quickly.
                    reserve = attempt is None or (
                        observed_failed and attempt.status == "failed" and attempt is observed
                    )
                    if reserve:
                        self._next_token += 1
                        attempt = _Attempt(self._next_token, key, Event(), Event())
                        self._evaluations[key] = attempt
                        self._current[resource] = attempt
                    assert attempt is not None
                    self._requests[request_key] = _RequestBinding(fingerprint, key)
                    break
            assert wait_for is not None
            wait_for.wait()  # never wait with the feedback lock held
        if reserve:
            self._admit(attempt, prepared)
        else:
            attempt.initial_done.wait()
        with self._feedback_lock:
            initial_failed = attempt.initial_failed
        if initial_failed:
            raise FeedbackAdmissionError()
        return FeedbackStartResponse(feedback_status="generating")

    def get_result(self, session_id: str, interview_id: str) -> FeedbackResult:
        """Read only: no scheduling, retry or status repair; return fresh report models."""
        self._flow.get(session_id, interview_id)
        with self._feedback_lock:
            attempt = self._current.get((session_id, interview_id))
            if attempt is None:
                return FeedbackResult("not_requested")
            status, report_json, error = attempt.status, attempt.report_json, attempt.error
        report = (
            FeedbackReport.model_validate_json(report_json) if report_json is not None else None
        )
        return FeedbackResult(status, report, error)

    def _owns(self, attempt: _Attempt) -> bool:
        """Called only under the feedback lock."""
        current = self._current.get(attempt.key[:2])
        return current is attempt and current.token == attempt.token

    def _failed_mirror(self, attempt: _Attempt) -> None:
        # Fixed failure is retained even if best-effort cleanup also fails.
        with suppress(Exception):
            self._flow.set_feedback_status(*attempt.key[:2], "failed")

    def _admit(self, attempt: _Attempt, prepared: PreparedFeedback) -> None:
        try:
            self._flow.set_feedback_status(*attempt.key[:2], "generating")
        except Exception:
            # Keep admission unresolved until its last status write is complete.
            self._failed_mirror(attempt)
            with self._feedback_lock:
                attempt.initial_failed = True
                attempt.status = "failed"
                attempt.error = _STATUS_FAILURE
                attempt.phase = "finished"
                attempt.finished.set()
                attempt.initial_done.set()
            return
        with self._feedback_lock:
            attempt.phase = "queued"
            attempt.initial_done.set()
        try:
            if self._runner is None:
                raise RuntimeError("No job runner configured")
            self._runner.submit(lambda: self._work(attempt, prepared))
        except Exception:
            self._finish(
                attempt,
                error=FeedbackFailure(
                    "feedback_job_unavailable", "Feedback could not be scheduled. Please retry."
                ),
            )

    def _work(self, attempt: _Attempt, prepared: PreparedFeedback) -> None:
        with self._feedback_lock:
            if not self._owns(attempt) or attempt.claimed or attempt.phase != "queued":
                return
            attempt.claimed = True
            attempt.phase = "running"
        try:
            report = self.evaluate(prepared)
            latest = self.prepare(*attempt.key[:2], prepared.request)
            if _evaluation_key(latest) != attempt.key:
                self._finish(
                    attempt,
                    error=FeedbackFailure(
                        "feedback_state_changed", "Interview state changed. Reload before retrying."
                    ),
                )
                return
            report_json = report.model_dump_json().encode("utf-8")
        except ProviderUnavailableError:
            self._finish(
                attempt,
                error=FeedbackFailure(
                    "feedback_provider_unavailable",
                    "Feedback provider is unavailable. Please retry.",
                ),
            )
        except ProviderProtocolError:
            self._finish(
                attempt,
                error=FeedbackFailure(
                    "feedback_invalid_assessment", "Feedback could not be validated. Please retry."
                ),
            )
        except InterviewError:
            self._finish(
                attempt,
                error=FeedbackFailure(
                    "feedback_state_changed", "Interview state changed. Reload before retrying."
                ),
            )
        except Exception:
            self._finish(
                attempt,
                error=FeedbackFailure(
                    "feedback_evaluation_failed", "Feedback evaluation failed. Please retry."
                ),
            )
        else:
            self._finish(attempt, report_json=report_json)

    def _finish(
        self,
        attempt: _Attempt,
        *,
        report_json: bytes | None = None,
        error: FeedbackFailure | None = None,
    ) -> None:
        with self._feedback_lock:
            if not self._owns(attempt) or attempt.phase not in {"queued", "running"}:
                return
            attempt.phase = "terminal"
        status: Literal["ready", "failed"] = "ready" if error is None else "failed"
        try:
            self._flow.set_feedback_status(*attempt.key[:2], status)
        except Exception:
            report_json, error, status = None, _STATUS_FAILURE, "failed"
            self._failed_mirror(attempt)
        with self._feedback_lock:
            if self._owns(attempt):
                attempt.status = status
                attempt.report_json = report_json if status == "ready" else None
                attempt.error = error
                attempt.phase = "finished"
            attempt.finished.set()

    def prepare(
        self, session_id: str, interview_id: str, request: FeedbackRequest
    ) -> PreparedFeedback:
        """Validate and project one stable completed attempt, without changing state."""
        request = FeedbackRequest.model_validate(request.model_dump())
        interview = self._flow.get(session_id, interview_id)
        if interview.phase != "completed":
            raise InterviewConflictError(
                "invalid_interview_phase",
                "Feedback requires a completed interview.",
                {"phase": interview.phase},
            )
        if interview.transcript_revision != request.expected_transcript_revision:
            raise InterviewConflictError(
                "transcript_revision_conflict",
                "The transcript changed. Reload and retry.",
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
                turn
                for turn in interview.turns
                if question.status == "answered"
                and turn.question_id == question.question_id
                and turn.turn_id in submitted
                and turn.speaker == "candidate"
                and turn.transcript_status == "final"
                and turn.text.strip()
            ]
            answer_turns.extend(turns)
            asked.append(
                QuestionAssessmentInput(
                    question_id=question.question_id,
                    text=question.text,
                    category=question.category,
                    answers=tuple(
                        FinalCandidateAnswerInput(turn.turn_id, turn.text) for turn in turns
                    ),
                )
            )

        assessment_input = FeedbackAssessmentInput(
            context=FeedbackContextInput(
                context.job.title, context.job.description, _candidate_context(context)
            ),
            questions=tuple(question for question in asked if question.answers),
        )
        return PreparedFeedback(
            request=request,
            interview=interview,
            context=context,
            submitted_turn_ids=submitted,
            asked_questions=tuple(asked),
            answer_turns=tuple(answer_turns),
            assessment_input=assessment_input,
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
        proposal = (
            self._provider.assess(inputs)
            if inputs.questions
            else ModelFeedbackAssessment(questions=[])
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
                        if canonical_question.status == "skipped"
                        else "No usable submitted final candidate answer is available "
                        "for this question."
                    )
                    combined.append(
                        ModelQuestionAssessment(
                            question_id=canonical_question.question_id,
                            criteria=[
                                CriterionFeedback(
                                    criterion=criterion,
                                    applicability=Applicability.INSUFFICIENT_EVIDENCE,
                                    score=None,
                                    evidence=[],
                                    explanation=explanation,
                                )
                                for criterion in CriterionName
                            ],
                        )
                    )
            return ModelFeedbackAssessment(questions=combined)
        except (ValidationError, _AssessmentContractError):
            raise ProviderProtocolError(_INVALID_ASSESSMENT) from None

    def evaluate(self, prepared: PreparedFeedback) -> FeedbackReport:
        """Construct a caller-owned report synchronously; do not save or change status."""
        snapshot = deepcopy(prepared)
        assessment = self.assess(snapshot)
        by_id = {question.question_id: question for question in assessment.questions}
        questions: list[QuestionFeedback] = []
        skipped = missing = transcription_incomplete = timing_unavailable = timing_partial = False
        for question in snapshot.interview.questions:
            if question.status == "planned":
                continue
            turns = [
                turn
                for turn in snapshot.answer_turns
                if question.status == "answered"
                and turn.question_id == question.question_id
                and turn.turn_id in snapshot.submitted_turn_ids
                and turn.speaker == "candidate"
                and turn.transcript_status == "final"
                and turn.text.strip()
            ]
            metrics = calculate_speaking_metrics(turns, question_id=question.question_id)
            wpm = metrics[0]
            usable_ids = {turn.turn_id for turn in turns if count_words(turn.text) > 0}
            skipped |= question.status == "skipped"
            missing |= not turns and question.status != "skipped"
            timing_unavailable |= wpm.status == "not_available"
            timing_partial |= wpm.status == "available" and set(wpm.turn_ids) != usable_ids
            transcription_incomplete |= any(
                turn.question_id == question.question_id
                and turn.speaker == "candidate"
                and turn.transcript_status in {"pending", "partial", "failed"}
                for turn in snapshot.interview.turns
            )
            criteria = {item.criterion: item for item in by_id[question.question_id].criteria}
            questions.append(
                QuestionFeedback(
                    question_id=question.question_id,
                    criteria=[criteria[name].model_copy(deep=True) for name in CriterionName],
                    speaking_metrics=metrics,
                )
            )
        # Fixed condition order and constant text: never include user data or parse methods.
        limitations = [
            message
            for applies, message in (
                (skipped, "Skipped questions have insufficient evidence and are not scored."),
                (missing, "Some asked questions have no usable submitted final candidate answer."),
                (
                    transcription_incomplete,
                    "Some candidate transcription for asked questions is incomplete or failed.",
                ),
                (
                    timing_unavailable,
                    "Words per minute is unavailable for some questions "
                    "without valid timed answers.",
                ),
                (
                    timing_partial,
                    "Some words-per-minute estimates cover only the subset of answers "
                    "with valid timing.",
                ),
                (
                    bool(questions),
                    "Transcript-based filler counts may reflect ASR errors "
                    "and omit spoken fillers.",
                ),
                (
                    bool(questions),
                    "Pause analysis is unavailable without analysed audio intervals "
                    "and a threshold.",
                ),
                (True, "Criterion feedback is automated coaching, not an employability decision."),
                (
                    True,
                    "Exact quote validation does not verify the truth of real-world answer claims.",
                ),
            )
            if applies
        ]
        return FeedbackReport(
            schema_version="1.0",
            rubric_version="1.0",
            report_id=self._report_id_factory(),
            interview_id=snapshot.interview.interview_id,
            context_hash=snapshot.interview.context_hash,
            transcript_revision=snapshot.interview.transcript_revision,
            generated_at=self._clock(),
            question_feedback=questions,
            limitations=list(dict.fromkeys(limitations)),
        )
