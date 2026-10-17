from __future__ import annotations

from pydantic import ValidationError

from app.domain.models import (
    Fact,
    FactStatus,
    ResumeEntry,
    ResumeEntryEdit,
    ResumeEntryStatus,
    ResumeEntryValidationIssue,
    Session,
    SessionState,
    ValidationSeverity,
)
from app.domain.workflow import (
    InvalidTransitionError,
    ResumeEntryNotFoundError,
    SessionWorkflow,
)
from app.providers.base import ProviderProtocolError, ResumeEntryProvider


class ResumeEntryEvidenceError(ValueError):
    pass


class ResumeEntryService:
    def __init__(self, workflow: SessionWorkflow, provider: ResumeEntryProvider) -> None:
        self._workflow = workflow
        self._provider = provider

    def propose(self, session_id: str) -> Session:
        session = self._workflow.get_session(session_id)
        if session.state in {SessionState.COLLECTING_PROFILE, SessionState.PROFILE_REVIEW}:
            raise InvalidTransitionError("Confirm the profile before proposing resume entries.")
        facts = self._confirmed_facts(session)
        if not facts:
            raise InvalidTransitionError("Confirm the profile before proposing resume entries.")
        entries = self._provider.propose_resume_entries(facts)
        if not isinstance(entries, list) or any(not isinstance(e, ResumeEntry) for e in entries):
            raise ProviderProtocolError("The model did not return structured resume entries.")
        if len({entry.entry_id for entry in entries}) != len(entries):
            raise ProviderProtocolError("Proposed resume entry IDs must be unique.")
        for entry in entries:
            if issues := self._entry_issues(session, entry):
                raise ResumeEntryEvidenceError(issues[0].message)
        return self._workflow.set_resume_entries(session_id, entries)

    def edit(self, session_id: str, entry_id: str, edit: ResumeEntryEdit) -> Session:
        session = self._workflow.get_session(session_id)
        entry = self._entry(session, entry_id)
        if issues := self._entry_issues(session, entry):
            raise ResumeEntryEvidenceError(issues[0].message)
        # Validate every replacement before the workflow changes the first display field.
        data = entry.model_dump()
        data["heading"]["text"] = edit.heading
        if data["organisation_or_context"] is not None:
            data["organisation_or_context"]["text"] = edit.organisation_or_context
        for detail, value in zip(data["details"], edit.details, strict=False):
            detail["value"]["text"] = value
        for bullet, value in zip(data["bullets"], edit.bullets, strict=False):
            bullet["text"] = value
        try:
            ResumeEntry.model_validate(data)
        except ValidationError as error:
            raise ResumeEntryEvidenceError("Resume entry display text is invalid.") from error
        prior_issues = [
            issue for issue in session.resume_entry_validation_issues if issue.entry_id != entry_id
        ]
        edited = self._workflow.update_resume_entry(session_id, entry_id, edit)
        edited.resume_entry_validation_issues = prior_issues
        return edited

    def approve(self, session_id: str, entry_id: str) -> Session:
        with self._workflow.lock_session(session_id) as session:
            snapshot = session.model_copy(deep=True)
            entry = self._entry(snapshot, entry_id)
            if issues := self._entry_issues(snapshot, entry):
                raise ResumeEntryEvidenceError(issues[0].message)
            if entry.status not in {ResumeEntryStatus.PROPOSED, ResumeEntryStatus.NEEDS_REVIEW}:
                raise InvalidTransitionError(
                    "Only a proposed or needs-review entry can be approved."
                )
        issues = self._provider.validate_resume_entries(
            [entry.model_copy(deep=True)], self._confirmed_facts(snapshot)
        )
        if not isinstance(issues, list) or any(
            not isinstance(issue, ResumeEntryValidationIssue) or issue.entry_id != entry_id
            for issue in issues
        ):
            raise ProviderProtocolError("The model returned an invalid resume entry audit.")
        try:
            issues = [
                ResumeEntryValidationIssue.model_validate(issue.model_dump(warnings=False))
                for issue in issues
            ]
        except ValidationError as error:
            raise ProviderProtocolError(
                "The model returned an invalid resume entry audit."
            ) from error
        if any(issue.severity is ValidationSeverity.ERROR for issue in issues):
            raise ResumeEntryEvidenceError(
                "This resume entry adds information not confirmed in your profile."
            )
        with self._workflow.lock_session(session_id) as session:
            current_entry = next(
                (item for item in session.resume_entries if item.entry_id == entry_id), None
            )
            current_issues = [
                issue for issue in session.resume_entry_validation_issues
                if issue.entry_id == entry_id
            ]
            audited_issues = [
                issue for issue in snapshot.resume_entry_validation_issues
                if issue.entry_id == entry_id
            ]
            if (
                session.resume_entries_revision != snapshot.resume_entries_revision
                or current_entry != entry
                or session.profile != snapshot.profile
                or current_issues != audited_issues
            ):
                raise InvalidTransitionError(
                    "This resume entry or its source facts changed during review. "
                    "Review the current entry and approve it again."
                )
            prior_issues = [
                issue for issue in session.resume_entry_validation_issues
                if issue.entry_id != entry_id
            ]
            approved = self._workflow.approve_resume_entry(session_id, entry_id, issues)
            approved.resume_entry_validation_issues = [*prior_issues, *issues]
            return approved

    def delete(self, session_id: str, entry_id: str) -> Session:
        return self._workflow.delete_resume_entry(session_id, entry_id)

    @staticmethod
    def _confirmed_facts(session: Session) -> list[Fact]:
        return [
            fact.model_copy(deep=True)
            for fact in session.profile.facts
            if fact.status is FactStatus.CONFIRMED
        ]

    @staticmethod
    def _entry(session: Session, entry_id: str) -> ResumeEntry:
        for entry in session.resume_entries:
            if entry.entry_id == entry_id:
                return entry
        raise ResumeEntryNotFoundError("The requested resume entry was not found.")

    @staticmethod
    def _entry_issues(session: Session, entry: ResumeEntry) -> list[ResumeEntryValidationIssue]:
        try:
            # Revalidate a dump because mutable/model_copy objects may bypass model validators.
            checked = ResumeEntry.model_validate(entry.model_dump())
        except ValidationError:
            return [
                ResumeEntryValidationIssue(
                    entry_id=entry.entry_id,
                    code="malformed_entry_evidence",
                    message=(
                        "Every visible item must cite a confirmed profile fact "
                        "with an exact source union."
                    ),
                )
            ]
        confirmed_ids = {
            fact.fact_id for fact in session.profile.facts if fact.status is FactStatus.CONFIRMED
        }
        if not set(checked.source_fact_ids).issubset(confirmed_ids):
            return [
                ResumeEntryValidationIssue(
                    entry_id=entry.entry_id,
                    code="unknown_fact_reference",
                    message=(
                        "Every resume entry citation must reference a confirmed "
                        "profile fact in this session."
                    ),
                )
            ]
        return []
