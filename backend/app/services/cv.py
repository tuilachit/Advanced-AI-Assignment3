from __future__ import annotations

import hashlib
import json

from app.domain.models import (
    CVClaim,
    CVDocument,
    FactStatus,
    Job,
    ResumeEntryKind,
    Session,
    SessionState,
    TraceEvent,
    ValidationIssue,
)
from app.domain.workflow import InvalidTransitionError, SessionWorkflow
from app.providers.base import CVProvider


class CVEvidenceError(ValueError):
    pass


def _all_claims(cv: CVDocument) -> list[CVClaim]:
    return [*cv.claims, *(claim for section in cv.sections for claim in section.claims)]


def cv_content_hash(cv: CVDocument) -> str:
    content = cv.model_dump(mode="json")
    for claim in content["claims"]:
        claim.pop("verified", None)
    for section in content["sections"]:
        for claim in section["claims"]:
            claim.pop("verified", None)
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CVService:
    def __init__(self, workflow: SessionWorkflow, provider: CVProvider) -> None:
        self._workflow = workflow
        self._provider = provider

    def generate(self, session_id: str, job: Job) -> CVDocument:
        with self._workflow.lock_session(session_id) as session:
            snapshot = session.model_copy(deep=True)
            workflow_revision = self._workflow.revision(session_id)
        if snapshot.state is not SessionState.JOB_SELECTED or not snapshot.selected_job_id:
            raise InvalidTransitionError("Select a retrieved job before generating a CV.")
        if job.document_id != snapshot.selected_job_id:
            raise InvalidTransitionError("The CV target must match the selected job.")

        approved_entries = self._workflow.approved_resume_entries(snapshot)
        if not any(
            entry.kind
            in {
                ResumeEntryKind.EXPERIENCE,
                ResumeEntryKind.PROJECT,
                ResumeEntryKind.EDUCATION,
                ResumeEntryKind.ACHIEVEMENT,
            }
            for entry in approved_entries
        ):
            raise InvalidTransitionError(
                "Approve a substantive resume entry before generating a CV."
            )
        contact_facts = [
            fact
            for fact in snapshot.profile.facts
            if fact.status is FactStatus.CONFIRMED
            and fact.field in {"name", "email", "phone", "github", "linkedin"}
        ]
        cv = self._provider.generate_cv(
            [fact.model_copy(deep=True) for fact in contact_facts],
            [entry.model_copy(deep=True) for entry in approved_entries],
            job.model_copy(deep=True),
        )
        if cv.target_job_id != job.document_id:
            raise CVEvidenceError("The generated CV targets the wrong job.")
        self._assert_claim_references(snapshot, cv)
        for claim in _all_claims(cv):
            claim.verified = False
        with self._workflow.lock_session(session_id) as session:
            if (
                self._workflow.revision(session_id) != workflow_revision
                or session.state is not SessionState.JOB_SELECTED
                or session.selected_job_id != snapshot.selected_job_id
                or session.profile != snapshot.profile
                or session.resume_entries != snapshot.resume_entries
            ):
                raise InvalidTransitionError(
                    "Your profile, resume entries, or selected job changed during generation. "
                    "Review the current entries and selected job, then generate a new CV."
                )
            session.cv = cv
            session.validation_issues = []
            session.validated_content_hash = None
            session.state = SessionState.CV_DRAFT
            session.trace.append(
                TraceEvent(
                    event_type="cv_generated",
                    summary="Generated an evidence-linked CV draft.",
                    details={"cv_id": cv.cv_id, "target_job_id": cv.target_job_id},
                )
            )
        return cv

    def update(self, session_id: str, cv_id: str, edited: CVDocument) -> Session:
        session = self._workflow.get_session(session_id)
        self._require_current_cv(session, cv_id)
        if edited.cv_id != cv_id:
            raise InvalidTransitionError("The edited CV ID must match the route CV ID.")
        if edited.target_job_id != session.selected_job_id:
            raise InvalidTransitionError("The edited CV must keep the selected target job.")
        self._assert_claim_references(session, edited)
        for claim in _all_claims(edited):
            claim.verified = False
        session.cv = edited
        session.validation_issues = []
        session.validated_content_hash = None
        session.state = SessionState.CV_DRAFT
        session.trace.append(
            TraceEvent(event_type="cv_updated", summary="User edited the CV draft.")
        )
        return session

    def validate(self, session_id: str, cv_id: str) -> Session:
        session = self._workflow.get_session(session_id)
        cv = self._require_current_cv(session, cv_id)
        deterministic_issues = self._claim_reference_issues(session, cv)
        semantic_issues = self._provider.validate_claims(
            cv,
            [fact for fact in session.profile.facts if fact.status is FactStatus.CONFIRMED],
        )
        session.validation_issues = [*deterministic_issues, *semantic_issues]
        has_error = any(issue.severity.value == "error" for issue in session.validation_issues)
        warning_count = sum(
            issue.severity.value == "warning" for issue in session.validation_issues
        )
        if has_error:
            for claim in _all_claims(cv):
                claim.verified = False
            session.validated_content_hash = None
            session.state = SessionState.CV_DRAFT
        else:
            for claim in _all_claims(cv):
                claim.verified = True
            session.validated_content_hash = cv_content_hash(cv)
            session.state = SessionState.CV_VALIDATED
        session.trace.append(
            TraceEvent(
                event_type="cv_validated",
                summary=(
                    "CV passed required evidence validation."
                    if not has_error
                    else "CV validation found blocking evidence issues."
                ),
                details={
                    "issue_count": len(session.validation_issues),
                    "warning_count": warning_count,
                },
            )
        )
        return session

    def can_export(self, session_id: str, cv_id: str) -> bool:
        session = self._workflow.get_session(session_id)
        if session.state not in {SessionState.CV_VALIDATED, SessionState.PDF_EXPORTED}:
            return False
        if session.cv is None or session.cv.cv_id != cv_id:
            return False
        return session.validated_content_hash == cv_content_hash(session.cv)

    def record_export(self, session_id: str, cv_id: str) -> Session:
        if not self.can_export(session_id, cv_id):
            raise InvalidTransitionError("Only the current validated CV can be exported.")
        session = self._workflow.get_session(session_id)
        session.state = SessionState.PDF_EXPORTED
        session.trace.append(
            TraceEvent(
                event_type="pdf_exported",
                summary="User exported the locally rendered PDF.",
                details={"cv_id": cv_id},
            )
        )
        return session

    @staticmethod
    def _require_current_cv(session: Session, cv_id: str) -> CVDocument:
        if session.cv is None or session.cv.cv_id != cv_id:
            raise InvalidTransitionError("The requested CV is not the current session CV.")
        return session.cv

    @staticmethod
    def _claim_reference_issues(session: Session, cv: CVDocument) -> list[ValidationIssue]:
        confirmed_ids = {
            fact.fact_id for fact in session.profile.facts if fact.status is FactStatus.CONFIRMED
        }
        issues: list[ValidationIssue] = []
        headline = CVClaim(claim_id="headline", text=cv.headline, fact_ids=cv.headline_fact_ids)
        for claim in [headline, *_all_claims(cv)]:
            if not claim.fact_ids:
                issues.append(
                    ValidationIssue(
                        claim_id=claim.claim_id,
                        code="missing_fact_reference",
                        message="Every factual CV claim must cite a confirmed profile fact.",
                    )
                )
            elif not set(claim.fact_ids).issubset(confirmed_ids):
                issues.append(
                    ValidationIssue(
                        claim_id=claim.claim_id,
                        code="unknown_fact_reference",
                        message="A CV claim cites an unknown or unconfirmed profile fact.",
                    )
                )
        return issues

    @classmethod
    def _assert_claim_references(cls, session: Session, cv: CVDocument) -> None:
        if issues := cls._claim_reference_issues(session, cv):
            raise CVEvidenceError(
                f"Generated CV contains {len(issues)} claim(s) without a confirmed fact."
            )
