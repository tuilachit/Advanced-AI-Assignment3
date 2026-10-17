from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from threading import RLock
from typing import Any, Concatenate, cast
from uuid import uuid4

from app.domain.models import (
    Fact,
    FactInput,
    FactSource,
    FactSourceType,
    FactStatus,
    ResumeEntry,
    ResumeEntryEdit,
    ResumeEntryKind,
    ResumeEntryStatus,
    ResumeEntryValidationIssue,
    ResumeText,
    RetrievalResult,
    Session,
    SessionState,
    TraceEvent,
)


class SessionNotFoundError(LookupError):
    pass


class ResumeEntryNotFoundError(LookupError):
    pass


class InvalidTransitionError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _session_mutation[**P](
    method: Callable[Concatenate[SessionWorkflow, str, P], Session],
) -> Callable[Concatenate[SessionWorkflow, str, P], Session]:
    @wraps(method)
    def locked(
        self: SessionWorkflow, session_id: str, *args: P.args, **kwargs: P.kwargs
    ) -> Session:
        with self.lock_session(session_id):
            result = method(self, session_id, *args, **kwargs)
            self._revisions[session_id] += 1
            return result

    return cast("Callable[Concatenate[SessionWorkflow, str, P], Session]", locked)


class SessionWorkflow:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._locks: dict[str, RLock] = {}
        self._revisions: dict[str, int] = {}

    def create_session(self) -> Session:
        session = Session(session_id=str(uuid4()))
        session.trace.append(
            TraceEvent(event_type="session_created", summary="Temporary session created.")
        )
        self._locks[session.session_id] = RLock()
        self._revisions[session.session_id] = 0
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise SessionNotFoundError(f"Session {session_id!r} was not found.") from error

    @contextmanager
    def lock_session(self, session_id: str) -> Iterator[Session]:
        """Protect short state reads/writes; release before calling a provider."""
        session = self.get_session(session_id)
        with self._locks[session_id]:
            yield session

    def revision(self, session_id: str) -> int:
        """Count workflow mutations, including selection of the same job again."""
        with self.lock_session(session_id):
            return self._revisions[session_id]

    @_session_mutation
    def update_profile(
        self,
        session_id: str,
        updates: list[FactInput],
        *,
        source_reference: str,
        source_type: FactSourceType = FactSourceType.USER_MESSAGE,
    ) -> Session:
        session = self.get_session(session_id)
        facts_by_field = {fact.field: fact for fact in session.profile.facts}
        changed_fact_ids: set[str] = set()

        for update in updates:
            source = FactSource(source_type=source_type, reference=source_reference)
            if current := facts_by_field.get(update.field):
                if current.value != update.value:
                    changed_fact_ids.add(current.fact_id)
                current.value = update.value
                current.status = FactStatus.DRAFT
                current.source = source
            else:
                fact = Fact(field=update.field, value=update.value, source=source)
                session.profile.facts.append(fact)
                facts_by_field[fact.field] = fact

        session.profile.revision += 1
        entry_status_changed = False
        if changed_fact_ids:
            for entry in session.resume_entries:
                if (
                    changed_fact_ids.intersection(entry.source_fact_ids)
                    and entry.status is not ResumeEntryStatus.NEEDS_REVIEW
                ):
                    entry.status = ResumeEntryStatus.NEEDS_REVIEW
                    entry_status_changed = True
        if entry_status_changed:
            session.resume_entries_revision += 1
        self._invalidate_downstream(session)
        session.state = (
            SessionState.PROFILE_REVIEW
            if session.profile.facts
            else SessionState.COLLECTING_PROFILE
        )
        session.trace.append(
            TraceEvent(
                event_type="profile_updated",
                summary=f"Updated {len(updates)} profile fact(s).",
                details={"fields": [update.field for update in updates]},
            )
        )
        return session

    @_session_mutation
    def confirm_profile(self, session_id: str) -> Session:
        session = self.get_session(session_id)
        missing_fields = self.missing_required_fields(session)
        if missing_fields:
            raise InvalidTransitionError(
                "The profile needs more information before confirmation.",
                details={"missing_fields": missing_fields},
            )

        for fact in session.profile.facts:
            fact.status = FactStatus.CONFIRMED
        if session.resume_entries:
            self._reconcile_resume_state(session)
        else:
            session.state = SessionState.PROFILE_CONFIRMED
        session.trace.append(
            TraceEvent(event_type="profile_confirmed", summary="User confirmed the profile facts.")
        )
        return session

    @_session_mutation
    def set_resume_entries(self, session_id: str, entries: list[ResumeEntry]) -> Session:
        session = self.get_session(session_id)
        allowed_states = {
            SessionState.PROFILE_CONFIRMED,
            SessionState.RESUME_ENTRIES_REVIEW,
            SessionState.RESUME_ENTRIES_APPROVED,
            SessionState.JOBS_RETRIEVED,
            SessionState.JOB_SELECTED,
            SessionState.CV_DRAFT,
            SessionState.CV_VALIDATED,
            SessionState.PDF_EXPORTED,
        }
        if session.state not in allowed_states:
            raise InvalidTransitionError(
                "Confirm the profile before proposing resume entries."
            )
        for entry in entries:
            self._ensure_confirmed_resume_entry_provenance(session, entry)
        session.resume_entries = [
            entry.model_copy(
                update={"status": ResumeEntryStatus.PROPOSED}, deep=True
            )
            for entry in entries
        ]
        session.resume_entries_revision += 1
        session.resume_entry_validation_issues = []
        self._invalidate_downstream(session)
        session.state = SessionState.RESUME_ENTRIES_REVIEW
        entry_count_summary = (
            "Proposed 1 resume entry."
            if len(entries) == 1
            else f"Proposed {len(entries)} resume entries."
        )
        session.trace.append(
            TraceEvent(
                event_type="resume_entries_proposed",
                summary=entry_count_summary,
                details={"entry_ids": [entry.entry_id for entry in session.resume_entries]},
            )
        )
        return session

    @_session_mutation
    def update_resume_entry(
        self, session_id: str, entry_id: str, edit: ResumeEntryEdit
    ) -> Session:
        session = self.get_session(session_id)
        entry = self._resume_entry(session, entry_id)
        if len(edit.details) != len(entry.details) or len(edit.bullets) != len(entry.bullets):
            raise InvalidTransitionError(
                "Resume entry edits must preserve the existing detail and bullet counts."
            )
        if (entry.organisation_or_context is None) != (edit.organisation_or_context is None):
            raise InvalidTransitionError(
                "Resume entry edits must preserve whether organisation or context is present."
            )

        entry.heading = ResumeText(text=edit.heading, fact_ids=entry.heading.fact_ids)
        if entry.organisation_or_context is not None:
            entry.organisation_or_context = ResumeText(
                text=edit.organisation_or_context or "",
                fact_ids=entry.organisation_or_context.fact_ids,
            )
        entry.details = [
            detail.model_copy(
                update={
                    "value": ResumeText(
                        text=value, fact_ids=detail.value.fact_ids
                    )
                }
            )
            for detail, value in zip(entry.details, edit.details, strict=True)
        ]
        entry.bullets = [
            ResumeText(text=text, fact_ids=bullet.fact_ids)
            for bullet, text in zip(entry.bullets, edit.bullets, strict=True)
        ]
        entry.status = ResumeEntryStatus.NEEDS_REVIEW
        session.resume_entries_revision += 1
        session.resume_entry_validation_issues = []
        self._invalidate_downstream(session)
        self._reconcile_resume_state(session)
        session.trace.append(
            TraceEvent(
                event_type="resume_entry_updated",
                summary="Updated a resume entry's display text.",
                details={"entry_id": entry_id},
            )
        )
        return session

    @_session_mutation
    def approve_resume_entry(
        self,
        session_id: str,
        entry_id: str,
        issues: list[ResumeEntryValidationIssue],
    ) -> Session:
        session = self.get_session(session_id)
        entry = self._resume_entry(session, entry_id)
        if entry.status not in {
            ResumeEntryStatus.PROPOSED,
            ResumeEntryStatus.NEEDS_REVIEW,
        }:
            raise InvalidTransitionError(
                "Only a proposed or needs-review resume entry can be approved."
            )
        if any(issue.entry_id != entry_id for issue in issues):
            raise InvalidTransitionError(
                "Resume entry validation issues must match the approved entry."
            )
        self._ensure_confirmed_resume_entry_provenance(session, entry)
        entry.status = ResumeEntryStatus.APPROVED
        session.resume_entries_revision += 1
        session.resume_entry_validation_issues = issues
        self._reconcile_resume_state(session)
        session.trace.append(
            TraceEvent(
                event_type="resume_entry_approved",
                summary="User approved a resume entry.",
                details={"entry_id": entry_id},
            )
        )
        return session

    @_session_mutation
    def delete_resume_entry(self, session_id: str, entry_id: str) -> Session:
        session = self.get_session(session_id)
        self._resume_entry(session, entry_id)
        session.resume_entries = [
            entry for entry in session.resume_entries if entry.entry_id != entry_id
        ]
        session.resume_entries_revision += 1
        session.resume_entry_validation_issues = [
            issue
            for issue in session.resume_entry_validation_issues
            if issue.entry_id != entry_id
        ]
        self._invalidate_downstream(session)
        self._reconcile_resume_state(session)
        session.trace.append(
            TraceEvent(
                event_type="resume_entry_removed",
                summary="Removed a resume entry.",
                details={"entry_id": entry_id},
            )
        )
        return session

    @staticmethod
    def approved_resume_entries(session: Session) -> list[ResumeEntry]:
        return [
            entry
            for entry in session.resume_entries
            if entry.status is ResumeEntryStatus.APPROVED
        ]

    def ensure_can_retrieve_jobs(self, session_id: str) -> Session:
        session = self.get_session(session_id)
        allowed_states = {
            SessionState.RESUME_ENTRIES_APPROVED,
            SessionState.JOBS_RETRIEVED,
            SessionState.JOB_SELECTED,
            SessionState.CV_DRAFT,
            SessionState.CV_VALIDATED,
            SessionState.PDF_EXPORTED,
        }
        if session.state not in allowed_states:
            raise InvalidTransitionError(
                "Approve a substantive resume entry before retrieving jobs."
            )
        return session

    @_session_mutation
    def set_retrieval_results(
        self, session_id: str, results: list[RetrievalResult]
    ) -> Session:
        session = self.ensure_can_retrieve_jobs(session_id)
        if not results:
            raise InvalidTransitionError("Job retrieval returned no results.")
        if len({result.document_id for result in results}) != len(results):
            raise InvalidTransitionError("Retrieved job IDs must be unique.")
        session.retrieval_results = results
        session.selected_job_id = None
        session.cv = None
        session.validation_issues = []
        session.validated_content_hash = None
        session.state = SessionState.JOBS_RETRIEVED
        session.trace.append(
            TraceEvent(
                event_type="jobs_retrieved",
                summary=f"Retrieved {len(results)} relevant job(s).",
                details={"document_ids": [result.document_id for result in results]},
            )
        )
        return session

    @_session_mutation
    def select_job(self, session_id: str, document_id: str) -> Session:
        session = self.get_session(session_id)
        retrieved_ids = {result.document_id for result in session.retrieval_results}
        if document_id not in retrieved_ids:
            raise InvalidTransitionError("The selected job must be one of the retrieved jobs.")
        session.selected_job_id = document_id
        session.cv = None
        session.validation_issues = []
        session.validated_content_hash = None
        session.state = SessionState.JOB_SELECTED
        session.trace.append(
            TraceEvent(
                event_type="job_selected",
                summary="User selected a target job.",
                details={"document_id": document_id},
            )
        )
        return session

    def missing_required_fields(self, session: Session) -> list[str]:
        fields = {fact.field for fact in session.profile.facts if fact.value.strip()}
        missing = [field for field in ("name", "education", "skills") if field not in fields]
        if not {"experience", "project"}.intersection(fields):
            missing.append("experience_or_project")
        if "target_role" not in fields:
            missing.append("target_role")
        return missing

    @staticmethod
    def _invalidate_downstream(session: Session) -> None:
        session.retrieval_results = []
        session.selected_job_id = None
        session.cv = None
        session.validation_issues = []
        session.validated_content_hash = None

    @staticmethod
    def _resume_entry(session: Session, entry_id: str) -> ResumeEntry:
        for entry in session.resume_entries:
            if entry.entry_id == entry_id:
                return entry
        raise ResumeEntryNotFoundError("The requested resume entry was not found.")

    @staticmethod
    def _ensure_confirmed_resume_entry_provenance(
        session: Session, entry: ResumeEntry
    ) -> None:
        confirmed_fact_ids = {
            fact.fact_id
            for fact in session.profile.facts
            if fact.status is FactStatus.CONFIRMED
        }
        nested_text = [entry.heading, *entry.bullets]
        if entry.organisation_or_context is not None:
            nested_text.append(entry.organisation_or_context)
        nested_text.extend(detail.value for detail in entry.details)
        referenced_fact_ids = list(
            dict.fromkeys(
                [
                    *entry.source_fact_ids,
                    *(fact_id for text in nested_text for fact_id in text.fact_ids),
                ]
            )
        )
        invalid_fact_ids = [
            fact_id for fact_id in referenced_fact_ids if fact_id not in confirmed_fact_ids
        ]
        if invalid_fact_ids:
            raise InvalidTransitionError(
                "Every resume entry citation must reference a confirmed fact in this session.",
                details={"entry_id": entry.entry_id, "invalid_fact_ids": invalid_fact_ids},
            )

    @staticmethod
    def _reconcile_resume_state(session: Session) -> None:
        substantive_kinds = {
            ResumeEntryKind.EXPERIENCE,
            ResumeEntryKind.PROJECT,
            ResumeEntryKind.EDUCATION,
            ResumeEntryKind.ACHIEVEMENT,
        }
        has_approved_substantive_entry = any(
            entry.status is ResumeEntryStatus.APPROVED and entry.kind in substantive_kinds
            for entry in session.resume_entries
        )
        session.state = (
            SessionState.RESUME_ENTRIES_APPROVED
            if has_approved_substantive_entry
            else SessionState.RESUME_ENTRIES_REVIEW
        )
