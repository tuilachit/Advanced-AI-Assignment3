"""Interview flow service (Interface Contract v1, sections 3-6 and 9).

Owns: the frozen context snapshot, the in-memory interview store, the question plan, the single
authority for question progression (follow-up limits, current question), time limits and the
interview lifecycle. Voice transport (Luke), feedback (Sunny) and UI (Mio) use this service.

Interviews live in memory like the existing sessions; a backend restart loses them.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from app.domain.interview_models import (
    AskQuestionStep,
    CreateInterviewRequest,
    FinishStep,
    Interview,
    InterviewConsent,
    InterviewContextSnapshot,
    InterviewControlRequest,
    InterviewJob,
    InterviewQuestion,
    NextStepRequest,
    PastedJobRequest,
    SkipQuestionRequest,
    StartInterviewRequest,
    StartInterviewResponse,
    TranscriptTurn,
    TurnEventAck,
    TurnEventRequest,
)
from app.domain.models import FactStatus, Job, ResumeEntryStatus, Session, SessionState
from app.domain.workflow import SessionWorkflow
from app.providers.base import ProviderProtocolError
from app.services.cv import cv_content_hash
from app.services.question_planner import QuestionPlanner, validate_plan

FINALIZE_DRAIN_SECONDS = 10
PLAN_ATTEMPTS = 2

_READY_FOR_INTERVIEW = {
    SessionState.RESUME_ENTRIES_APPROVED,
    SessionState.JOBS_RETRIEVED,
    SessionState.JOB_SELECTED,
    SessionState.CV_DRAFT,
    SessionState.CV_VALIDATED,
    SessionState.PDF_EXPORTED,
}


# ---------------------------------------------------------------------------
# Errors (mapped to the existing {"error": {...}} envelope by the API layer)
# ---------------------------------------------------------------------------


class InterviewError(Exception):
    status_code = 409

    def __init__(
        self, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class InterviewNotFoundError(InterviewError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("interview_not_found", "The requested interview was not found.")


class InterviewJobNotFoundError(InterviewError):
    status_code = 404

    def __init__(self, document_id: str) -> None:
        super().__init__(
            "job_not_found",
            "The selected job does not exist in the supplied job list.",
            {"document_id": document_id},
        )


class InterviewConflictError(InterviewError):
    status_code = 409


class QuestionPlanError(ProviderProtocolError):
    """The planner could not produce a valid plan; surfaces as a recoverable 503."""


# ---------------------------------------------------------------------------
# Internal record
# ---------------------------------------------------------------------------


def _fingerprint(model: BaseModel) -> str:
    return hashlib.sha256(model.model_dump_json().encode("utf-8")).hexdigest()


def context_hash(snapshot: InterviewContextSnapshot) -> str:
    canonical = json.dumps(
        snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class _InterviewRecord:
    interview: Interview
    context: InterviewContextSnapshot
    consent: InterviewConsent
    create_fingerprint: str
    deadline_at: datetime | None = None
    drain_until: datetime | None = None
    active_connection_id: str | None = None
    responses: dict[str, tuple[str, BaseModel]] = field(default_factory=dict)
    events: dict[str, tuple[str, TurnEventAck]] = field(default_factory=dict)
    previous_turn: dict[str, str | None] = field(default_factory=dict)
    consumed_turn_ids: set[str] = field(default_factory=set)


class InterviewFlowService:
    def __init__(
        self,
        workflow: SessionWorkflow,
        jobs: list[Job],
        planner: QuestionPlanner,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._workflow = workflow
        self._jobs = {job.document_id: job for job in jobs}
        self._planner = planner
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, _InterviewRecord] = {}
        self._create_keys: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ helpers

    def _now(self) -> datetime:
        return self._clock()

    @contextmanager
    def _record(self, session_id: str, interview_id: str) -> Iterator[_InterviewRecord]:
        with self._lock:
            record = self._records.get(interview_id)
            if record is None or record.interview.session_id != session_id:
                raise InterviewNotFoundError()
            self._advance_clock(record)
            yield record

    @staticmethod
    def _replay(record: _InterviewRecord, request_id: str, fingerprint: str) -> BaseModel | None:
        stored = record.responses.get(request_id)
        if stored is None:
            return None
        if stored[0] != fingerprint:
            raise InterviewConflictError(
                "request_id_conflict",
                "This request_id was already used with different input.",
                {"request_id": request_id},
            )
        return stored[1].model_copy(deep=True)

    @staticmethod
    def _remember(
        record: _InterviewRecord, request_id: str, fingerprint: str, response: BaseModel
    ) -> None:
        record.responses[request_id] = (fingerprint, response.model_copy(deep=True))

    @staticmethod
    def _check_revision(record: _InterviewRecord, expected: int) -> None:
        if expected != record.interview.flow_revision:
            raise InterviewConflictError(
                "flow_revision_conflict",
                "The interview changed since this request was prepared. Reload and retry.",
                {"flow_revision": record.interview.flow_revision},
            )

    @staticmethod
    def _check_connection(record: _InterviewRecord, connection_id: str | None) -> None:
        if (
            connection_id is not None
            and record.active_connection_id is not None
            and connection_id != record.active_connection_id
        ):
            raise InterviewConflictError(
                "stale_connection", "This voice connection is no longer active."
            )

    @staticmethod
    def _require_phase(record: _InterviewRecord, *phases: str) -> None:
        if record.interview.phase not in phases:
            raise InterviewConflictError(
                "invalid_interview_phase",
                f"This action is not allowed while the interview is {record.interview.phase}.",
                {"phase": record.interview.phase},
            )

    @staticmethod
    def _question(record: _InterviewRecord, question_id: str) -> InterviewQuestion:
        for question in record.interview.questions:
            if question.question_id == question_id:
                return question
        raise InterviewConflictError(
            "unknown_question", "The question does not belong to this interview.",
            {"question_id": question_id},
        )

    @staticmethod
    def _turn(record: _InterviewRecord, turn_id: str) -> TranscriptTurn | None:
        return next((t for t in record.interview.turns if t.turn_id == turn_id), None)

    # ------------------------------------------------------------------ create

    def create(self, session_id: str, request: CreateInterviewRequest) -> Interview:
        fingerprint = _fingerprint(request)
        with self._lock:
            existing_id = self._create_keys.get((session_id, request.request_id))
            if existing_id is not None:
                record = self._records[existing_id]
                if record.create_fingerprint != fingerprint:
                    raise InterviewConflictError(
                        "request_id_conflict",
                        "This request_id was already used with different input.",
                        {"request_id": request.request_id},
                    )
                return record.interview.model_copy(deep=True)

        session = self._workflow.get_session(session_id)
        context, profile_revision, entries_revision, cv_hash = self._freeze_context(
            session, request
        )
        questions = self._plan(context)
        now = self._now()
        interview = Interview(
            session_id=session_id,
            interview_id=f"interview-{uuid4()}",
            phase="ready",
            flow_revision=0,
            transcript_revision=0,
            context_hash=context_hash(context),
            profile_revision=profile_revision,
            resume_entries_revision=entries_revision,
            cv_id=request.cv_id,
            cv_content_hash=cv_hash,
            job=context.job,
            config=context.config,
            questions=questions,
            current_question_id=None,
            turns=[],
            feedback_status="not_requested",
            created_at=now,
            started_at=None,
            ended_at=None,
            end_reason=None,
        )
        with self._lock:
            # A concurrent identical request may have finished first; keep only one.
            existing_id = self._create_keys.get((session_id, request.request_id))
            if existing_id is not None:
                return self._records[existing_id].interview.model_copy(deep=True)
            self._records[interview.interview_id] = _InterviewRecord(
                interview=interview,
                context=context,
                consent=request.consent,
                create_fingerprint=fingerprint,
            )
            self._create_keys[(session_id, request.request_id)] = interview.interview_id
        return interview.model_copy(deep=True)

    def _freeze_context(
        self, session: Session, request: CreateInterviewRequest
    ) -> tuple[InterviewContextSnapshot, int, int, str | None]:
        if session.state not in _READY_FOR_INTERVIEW:
            raise InterviewConflictError(
                "interview_not_ready",
                "Confirm your profile and approve your resume entries before practising.",
                {"state": session.state.value},
            )
        facts = [
            fact.model_copy(deep=True)
            for fact in session.profile.facts
            if fact.status is FactStatus.CONFIRMED
        ]
        entries = [
            entry.model_copy(deep=True)
            for entry in session.resume_entries
            if entry.status is ResumeEntryStatus.APPROVED
        ]
        if not facts or not entries:
            raise InterviewConflictError(
                "interview_not_ready",
                "Confirm your profile and approve at least one resume entry before practising.",
            )

        cv = None
        cv_hash = None
        if request.cv_id is not None:
            current = session.cv
            if (
                current is None
                or current.cv_id != request.cv_id
                or session.state not in {SessionState.CV_VALIDATED, SessionState.PDF_EXPORTED}
                or session.validated_content_hash != cv_content_hash(current)
            ):
                raise InterviewConflictError(
                    "cv_not_validated",
                    "Use the current validated CV, or start the interview without a CV.",
                    {"cv_id": request.cv_id},
                )
            cv = current.model_copy(deep=True)
            cv_hash = session.validated_content_hash

        if isinstance(request.job, PastedJobRequest):
            job = InterviewJob(
                source="pasted_job",
                document_id=None,
                title=request.job.title,
                description=request.job.description,
            )
        else:
            supplied = self._jobs.get(request.job.document_id)
            if supplied is None:
                raise InterviewJobNotFoundError(request.job.document_id)
            job = InterviewJob(
                source="supplied_job",
                document_id=supplied.document_id,
                title=supplied.title,
                description=supplied.description,
            )

        context = InterviewContextSnapshot(
            confirmed_facts=facts,
            approved_entries=entries,
            cv=cv,
            job=job,
            config=request.config.model_copy(deep=True),
        )
        return context, session.profile.revision, session.resume_entries_revision, cv_hash

    def _plan(self, context: InterviewContextSnapshot) -> list[InterviewQuestion]:
        problems: list[str] | None = None
        for _attempt in range(PLAN_ATTEMPTS):
            planned = self._planner.plan_questions(context, problems=problems)
            result = validate_plan(context, planned)
            if result.ok:
                return [
                    InterviewQuestion(
                        question_id=f"question-{uuid4()}",
                        parent_question_id=None,
                        kind="main",
                        category=item.category,
                        status="planned",
                        text=item.text,
                        rationale=item.rationale,
                        fact_ids=item.fact_ids,
                        resume_entry_ids=item.resume_entry_ids,
                        job_requirement_excerpt=item.job_requirement_excerpt,
                    )
                    for item in result.questions
                ]
            problems = result.problems
        raise QuestionPlanError(
            "The interview questions could not be prepared. Please try again."
        )

    # ------------------------------------------------------------------ reads

    def get(self, session_id: str, interview_id: str) -> Interview:
        with self._record(session_id, interview_id) as record:
            return record.interview.model_copy(deep=True)

    def get_context(self, session_id: str, interview_id: str) -> InterviewContextSnapshot:
        """Frozen context for the feedback service (server-side only)."""
        with self._record(session_id, interview_id) as record:
            return record.context.model_copy(deep=True)

    def get_consent(self, session_id: str, interview_id: str) -> InterviewConsent:
        with self._record(session_id, interview_id) as record:
            return record.consent.model_copy()

    def submitted_turn_ids(self, session_id: str, interview_id: str) -> set[str]:
        """Candidate turns that were explicitly submitted as answers (for feedback)."""
        with self._record(session_id, interview_id) as record:
            return set(record.consumed_turn_ids)

    def set_feedback_status(self, session_id: str, interview_id: str, status: str) -> Interview:
        with self._record(session_id, interview_id) as record:
            record.interview.feedback_status = status  # type: ignore[assignment]
            return record.interview.model_copy(deep=True)

    def bind_connection(self, session_id: str, interview_id: str) -> str:
        """Create a new voice connection ID for an active interview (used by the token route).

        Any earlier connection becomes obsolete: it can no longer create turns or advance flow.
        """
        with self._record(session_id, interview_id) as record:
            self._require_phase(record, "active")
            record.active_connection_id = f"connection-{uuid4()}"
            return record.active_connection_id

    # ------------------------------------------------------------------ lifecycle

    def start(
        self, session_id: str, interview_id: str, request: StartInterviewRequest
    ) -> StartInterviewResponse:
        fingerprint = _fingerprint(request)
        with self._record(session_id, interview_id) as record:
            if (replay := self._replay(record, request.request_id, fingerprint)) is not None:
                return StartInterviewResponse.model_validate(replay.model_dump())
            self._check_revision(record, request.expected_flow_revision)
            self._require_phase(record, "ready")
            consent = record.consent
            if not (consent.send_audio_to_provider and consent.retain_transcript_for_feedback):
                raise InterviewConflictError(
                    "consent_required",
                    "Agree to send audio to the provider and keep the transcript for feedback "
                    "before starting the live interview.",
                )
            now = self._now()
            interview = record.interview
            interview.phase = "active"
            interview.started_at = now
            record.deadline_at = now + timedelta(minutes=interview.config.duration_minutes)
            if request.connection_id is not None:
                record.active_connection_id = request.connection_id
            first = next(q for q in interview.questions if q.kind == "main")
            first.status = "issued"
            interview.current_question_id = first.question_id
            interview.flow_revision += 1
            response = StartInterviewResponse(
                interview=interview.model_copy(deep=True),
                next_step=AskQuestionStep(
                    action="ask_question",
                    question=first.model_copy(),
                    flow_revision=interview.flow_revision,
                ),
            )
            self._remember(record, request.request_id, fingerprint, response)
            return response

    def next_step(
        self, session_id: str, interview_id: str, request: NextStepRequest
    ) -> AskQuestionStep | FinishStep:
        fingerprint = _fingerprint(request)
        with self._record(session_id, interview_id) as record:
            if (replay := self._replay(record, request.request_id, fingerprint)) is not None:
                return replay  # type: ignore[return-value]
            if (
                record.interview.phase in {"finalizing", "completed"}
                and record.interview.end_reason == "time_limit"
            ):
                # The deadline passed before this request: the server already finalized and
                # submitted the captured answer, so tell the adapter to stop asking.
                finish = FinishStep(
                    action="finish",
                    reason="time_limit",
                    flow_revision=record.interview.flow_revision,
                )
                self._remember(record, request.request_id, fingerprint, finish)
                return finish
            self._check_revision(record, request.expected_flow_revision)
            self._check_connection(record, request.connection_id)
            self._require_phase(record, "active")
            interview = record.interview
            if request.answered_question_id != interview.current_question_id:
                raise InterviewConflictError(
                    "question_not_current",
                    "Only the current question can be answered.",
                    {"current_question_id": interview.current_question_id},
                )
            question = self._question(record, request.answered_question_id)
            self._consume_answer(record, question, request.answer_turn_ids)

            interview.flow_revision += 1
            step = self._choose_next(record, question, request)
            self._remember(record, request.request_id, fingerprint, step)
            return step

    def skip(
        self, session_id: str, interview_id: str, request: SkipQuestionRequest
    ) -> AskQuestionStep | FinishStep:
        fingerprint = _fingerprint(request)
        with self._record(session_id, interview_id) as record:
            if (replay := self._replay(record, request.request_id, fingerprint)) is not None:
                return replay  # type: ignore[return-value]
            self._check_revision(record, request.expected_flow_revision)
            self._check_connection(record, request.connection_id)
            self._require_phase(record, "active")
            interview = record.interview
            if request.question_id != interview.current_question_id:
                raise InterviewConflictError(
                    "question_not_current",
                    "Only the current question can be skipped.",
                    {"current_question_id": interview.current_question_id},
                )
            question = self._question(record, request.question_id)
            question.status = "skipped"
            interview.flow_revision += 1
            step = self._advance_main(record)
            self._remember(record, request.request_id, fingerprint, step)
            return step

    def end(
        self, session_id: str, interview_id: str, request: InterviewControlRequest
    ) -> Interview:
        fingerprint = _fingerprint(request)
        with self._record(session_id, interview_id) as record:
            if (replay := self._replay(record, request.request_id, fingerprint)) is not None:
                return Interview.model_validate(replay.model_dump())
            self._check_revision(record, request.expected_flow_revision)
            self._check_connection(record, request.connection_id)
            self._require_phase(record, "active")
            record.interview.flow_revision += 1
            self._begin_finalization(record, "user_finished")
            response = record.interview.model_copy(deep=True)
            self._remember(record, request.request_id, fingerprint, response)
            return response

    def cancel(
        self, session_id: str, interview_id: str, request: InterviewControlRequest
    ) -> Interview:
        fingerprint = _fingerprint(request)
        with self._record(session_id, interview_id) as record:
            if (replay := self._replay(record, request.request_id, fingerprint)) is not None:
                return Interview.model_validate(replay.model_dump())
            self._check_revision(record, request.expected_flow_revision)
            self._check_connection(record, request.connection_id)
            self._require_phase(record, "ready", "active")
            interview = record.interview
            interview.phase = "cancelled"
            interview.end_reason = "user_cancelled"
            interview.ended_at = self._now()
            interview.current_question_id = None
            interview.flow_revision += 1
            record.active_connection_id = None
            response = interview.model_copy(deep=True)
            self._remember(record, request.request_id, fingerprint, response)
            return response

    def fail(self, session_id: str, interview_id: str) -> Interview:
        """Mark an unrecoverable provider failure (for the voice adapter); keeps all records."""
        with self._record(session_id, interview_id) as record:
            self._require_phase(record, "ready", "active", "finalizing")
            interview = record.interview
            interview.phase = "failed"
            interview.end_reason = "provider_failure"
            interview.ended_at = interview.ended_at or self._now()
            interview.current_question_id = None
            interview.flow_revision += 1
            record.active_connection_id = None
            return interview.model_copy(deep=True)

    # ------------------------------------------------------------------ progression

    def _consume_answer(
        self, record: _InterviewRecord, question: InterviewQuestion, turn_ids: list[str]
    ) -> None:
        unique_ids = list(dict.fromkeys(turn_ids))
        pending: list[str] = []
        failed: list[str] = []
        for turn_id in unique_ids:
            turn = self._turn(record, turn_id)
            if (
                turn is None
                or turn.speaker != "candidate"
                or turn.question_id != question.question_id
            ):
                raise InterviewConflictError(
                    "invalid_answer_turn",
                    "Answer turns must be candidate turns registered for this question.",
                    {"turn_id": turn_id},
                )
            if turn_id in record.consumed_turn_ids:
                raise InterviewConflictError(
                    "answer_already_submitted",
                    "This answer was already submitted.",
                    {"turn_id": turn_id},
                )
            if turn.transcript_status in {"pending", "partial"}:
                pending.append(turn_id)
            elif turn.transcript_status == "failed" or not turn.text.strip():
                failed.append(turn_id)
        if pending:
            raise InterviewConflictError(
                "transcript_pending",
                "Your last answer is still being transcribed.",
                {"retryable": True, "turn_ids": pending},
            )
        if failed:
            raise InterviewConflictError(
                "transcript_failed",
                "Your answer could not be transcribed. Retry the answer, skip the question or "
                "finish the interview.",
                {"retryable": False, "turn_ids": failed},
            )
        record.consumed_turn_ids.update(unique_ids)
        question.status = "answered"

    def _choose_next(
        self,
        record: _InterviewRecord,
        answered: InterviewQuestion,
        request: NextStepRequest,
    ) -> AskQuestionStep | FinishStep:
        interview = record.interview
        if self._time_is_up(record):
            interview.current_question_id = None
            self._begin_finalization(record, "time_limit")
            return FinishStep(
                action="finish", reason="time_limit", flow_revision=interview.flow_revision
            )
        proposal = request.follow_up_proposal
        root_id = answered.parent_question_id or answered.question_id
        follow_ups = [q for q in interview.questions if q.parent_question_id == root_id]
        existing_texts = {" ".join(q.text.split()).casefold() for q in interview.questions}
        if (
            proposal is not None
            and len(follow_ups) < interview.config.max_follow_ups_per_question
            and " ".join(proposal.text.split()).casefold() not in existing_texts
        ):
            root = self._question(record, root_id)
            follow_up = InterviewQuestion(
                question_id=f"question-{uuid4()}",
                parent_question_id=root_id,
                kind="follow_up",
                category=root.category,
                status="issued",
                text=proposal.text,
                rationale=proposal.rationale,
                fact_ids=[],
                resume_entry_ids=[],
                job_requirement_excerpt=None,
            )
            # Keep follow-ups next to their main question in the list.
            position = max(
                index
                for index, q in enumerate(interview.questions)
                if q.question_id == root_id or q.parent_question_id == root_id
            )
            interview.questions.insert(position + 1, follow_up)
            interview.current_question_id = follow_up.question_id
            return AskQuestionStep(
                action="ask_question",
                question=follow_up.model_copy(),
                flow_revision=interview.flow_revision,
            )
        return self._advance_main(record)

    def _advance_main(self, record: _InterviewRecord) -> AskQuestionStep | FinishStep:
        interview = record.interview
        if self._time_is_up(record):
            interview.current_question_id = None
            self._begin_finalization(record, "time_limit")
            return FinishStep(
                action="finish", reason="time_limit", flow_revision=interview.flow_revision
            )
        upcoming = next(
            (q for q in interview.questions if q.kind == "main" and q.status == "planned"), None
        )
        if upcoming is None:
            interview.current_question_id = None
            self._begin_finalization(record, "questions_complete")
            return FinishStep(
                action="finish",
                reason="questions_complete",
                flow_revision=interview.flow_revision,
            )
        upcoming.status = "issued"
        interview.current_question_id = upcoming.question_id
        return AskQuestionStep(
            action="ask_question",
            question=upcoming.model_copy(),
            flow_revision=interview.flow_revision,
        )

    # ------------------------------------------------------------------ time and finalization

    def _time_is_up(self, record: _InterviewRecord) -> bool:
        return record.deadline_at is not None and self._now() >= record.deadline_at

    def _advance_clock(self, record: _InterviewRecord) -> None:
        """Enforce the deadline and finish draining whenever the interview is touched."""
        if record.interview.phase == "active" and self._time_is_up(record):
            record.interview.flow_revision += 1
            self._begin_finalization(record, "time_limit")
        if record.interview.phase == "finalizing":
            self._maybe_complete(record)

    def _begin_finalization(self, record: _InterviewRecord, reason: str) -> None:
        interview = record.interview
        interview.phase = "finalizing"
        interview.end_reason = reason  # type: ignore[assignment]
        interview.ended_at = self._now()
        record.drain_until = interview.ended_at + timedelta(seconds=FINALIZE_DRAIN_SECONDS)
        self._maybe_complete(record)

    def _maybe_complete(self, record: _InterviewRecord) -> None:
        interview = record.interview
        current_id = interview.current_question_id
        current = (
            next((q for q in interview.questions if q.question_id == current_id), None)
            if current_id
            else None
        )
        waiting = [
            turn
            for turn in interview.turns
            if turn.transcript_status in {"pending", "partial"}
        ]
        drained = record.drain_until is not None and self._now() >= record.drain_until
        if waiting and not drained:
            return
        changed = False
        for turn in waiting:
            # Never invent text: an unfinished transcript is recorded as failed.
            turn.transcript_status = "failed"
            changed = True
        if changed:
            interview.transcript_revision += 1
        if current is not None and current.status == "issued":
            # Submit the last answer once, even though no next-step request was made.
            final_ids = [
                turn.turn_id
                for turn in interview.turns
                if turn.question_id == current.question_id
                and turn.speaker == "candidate"
                and turn.transcript_status == "final"
                and turn.text.strip()
                and turn.turn_id not in record.consumed_turn_ids
            ]
            if final_ids:
                record.consumed_turn_ids.update(final_ids)
                current.status = "answered"
        interview.current_question_id = None
        interview.phase = "completed"
        record.active_connection_id = None

    # ------------------------------------------------------------------ transcript turns

    def record_turn(
        self, session_id: str, interview_id: str, event: TurnEventRequest
    ) -> TurnEventAck:
        fingerprint = _fingerprint(event)
        with self._record(session_id, interview_id) as record:
            stored = record.events.get(event.event_id)
            if stored is not None:
                if stored[0] != fingerprint:
                    raise InterviewConflictError(
                        "event_id_conflict",
                        "This event_id was already used with different content.",
                        {"event_id": event.event_id},
                    )
                return stored[1].model_copy()

            interview = record.interview
            incoming = event.turn
            existing = self._turn(record, incoming.turn_id)
            if existing is None:
                self._register_new_turn(record, event)
            else:
                self._update_turn(record, existing, event)
            ack = TurnEventAck(
                event_id=event.event_id,
                turn_id=incoming.turn_id,
                transcript_revision=interview.transcript_revision,
            )
            record.events[event.event_id] = (fingerprint, ack)
            if interview.phase == "finalizing":
                self._maybe_complete(record)
            return ack.model_copy()

    def _register_new_turn(self, record: _InterviewRecord, event: TurnEventRequest) -> None:
        interview = record.interview
        turn = event.turn
        self._require_phase(record, "active")
        if record.active_connection_id is not None and (
            event.connection_id != record.active_connection_id
        ):
            raise InterviewConflictError(
                "stale_connection", "This voice connection is no longer active."
            )
        if turn.question_id != interview.current_question_id:
            raise InterviewConflictError(
                "question_not_current",
                "New speech must be registered against the current question.",
                {"current_question_id": interview.current_question_id},
            )
        if event.previous_turn_id is None:
            if interview.turns:
                raise InterviewConflictError(
                    "invalid_turn_order", "Only the first turn may omit previous_turn_id."
                )
            position = 0
        else:
            indexes = [
                i for i, t in enumerate(interview.turns) if t.turn_id == event.previous_turn_id
            ]
            if not indexes:
                raise InterviewConflictError(
                    "predecessor_pending",
                    "The previous turn is not registered yet. Retry after it is stored.",
                    {"retryable": True, "previous_turn_id": event.previous_turn_id},
                )
            if event.previous_turn_id in record.previous_turn.values():
                raise InterviewConflictError(
                    "invalid_turn_order", "Another turn already follows the previous turn."
                )
            position = indexes[0] + 1
        interview.turns.insert(position, turn.model_copy(deep=True))
        record.previous_turn[turn.turn_id] = event.previous_turn_id
        interview.transcript_revision += 1

    def _update_turn(
        self, record: _InterviewRecord, existing: TranscriptTurn, event: TurnEventRequest
    ) -> None:
        interview = record.interview
        incoming = event.turn
        self._require_phase(record, "active", "finalizing")
        if (
            existing.speaker != incoming.speaker
            or existing.question_id != incoming.question_id
            or existing.input_mode != incoming.input_mode
        ):
            raise InterviewConflictError(
                "turn_identity_conflict",
                "A turn cannot change its speaker, question or input mode.",
                {"turn_id": incoming.turn_id},
            )
        if record.previous_turn.get(incoming.turn_id) != event.previous_turn_id:
            raise InterviewConflictError(
                "invalid_turn_order", "A turn cannot change its position in the conversation."
            )
        if incoming.turn_id in record.consumed_turn_ids:
            if incoming == existing:
                return
            raise InterviewConflictError(
                "answer_already_submitted",
                "A submitted answer cannot be changed.",
                {"turn_id": incoming.turn_id},
            )
        if incoming.transcript_version < existing.transcript_version:
            return  # an older replacement arriving late is ignored
        if incoming.transcript_version == existing.transcript_version:
            if incoming == existing:
                return
            raise InterviewConflictError(
                "transcript_version_conflict",
                "Different content was sent with the same transcript_version.",
                {"turn_id": incoming.turn_id},
            )
        if existing.transcript_status == "final" and incoming.transcript_status != "final":
            raise InterviewConflictError(
                "transcript_final",
                "A final transcript cannot be replaced by a partial one.",
                {"turn_id": incoming.turn_id},
            )
        index = interview.turns.index(existing)
        interview.turns[index] = incoming.model_copy(deep=True)
        interview.transcript_revision += 1
