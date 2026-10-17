from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from pydantic import Field, model_validator

from app.domain.models import (
    Fact,
    FactSource,
    FactSourceType,
    FactStatus,
    ResumeEntry,
    ResumeEntryValidationIssue,
    Session,
    SessionState,
    StrictModel,
    TraceEvent,
)


def profile_to_confirmed_facts(
    profile: Mapping[str, object], profile_id: str
) -> list[Fact]:
    source = FactSource(
        source_type=FactSourceType.IMPORTED_TEST_PROFILE,
        reference=profile_id,
    )
    facts: list[Fact] = []
    if education := profile.get("education") or profile.get("degree"):
        facts.append(
            Fact(
                fact_id=f"fact-{profile_id}-education",
                field="education",
                value=str(education),
                status=FactStatus.CONFIRMED,
                source=source,
            )
        )
    skills = profile.get("skills") or profile.get("technical_skills")
    if isinstance(skills, Sequence) and not isinstance(skills, str) and skills:
        facts.append(
            Fact(
                fact_id=f"fact-{profile_id}-skills",
                field="skills",
                value=", ".join(str(skill) for skill in skills),
                status=FactStatus.CONFIRMED,
                source=source,
            )
        )
    for profile_field, fact_field in (("projects", "project"), ("experience", "experience")):
        if items := profile.get(profile_field):
            facts.append(
                Fact(
                    fact_id=f"fact-{profile_id}-{fact_field}",
                    field=fact_field,
                    value=json.dumps(
                        items,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    status=FactStatus.CONFIRMED,
                    source=source,
                )
            )
    target_role = profile.get("target_role")
    target_roles = profile.get("target_roles")
    if not target_role and isinstance(target_roles, Sequence) and not isinstance(
        target_roles, str
    ):
        target_role = target_roles[0] if target_roles else None
    if target_role:
        facts.append(
            Fact(
                fact_id=f"fact-{profile_id}-target-role",
                field="target_role",
                value=str(target_role),
                status=FactStatus.CONFIRMED,
                source=source,
            )
        )
    return facts


def export_outcome(state: SessionState) -> str:
    return "exported" if state is SessionState.PDF_EXPORTED else "blocked"


def _contains_sensitive_text(value: object) -> bool:
    if isinstance(value, str):
        normalized = value.lower()
        return any(prefix in normalized for prefix in ("sk-", "resp_", "chatcmpl-", "cmpl-"))
    if isinstance(value, Mapping):
        return any(
            _contains_sensitive_text(item) for pair in value.items() for item in pair
        )
    if isinstance(value, Sequence) and not isinstance(value, str):
        return any(_contains_sensitive_text(item) for item in value)
    return False


class LiveModelConfiguration(StrictModel):
    chat_model: str
    embedding_model: str


class LiveMessage(StrictModel):
    role: str
    content: str


class LiveRetrievalResult(StrictModel):
    document_id: str
    score: float
    excerpt: str


class LiveTransition(StrictModel):
    from_state: str
    to_state: str


class LiveValidationIssue(StrictModel):
    code: str
    message: str


class LiveCVResult(StrictModel):
    selected_job_id: str
    validation_issues: list[LiveValidationIssue] = Field(default_factory=list)
    export_outcome: str


class LiveRunRecord(StrictModel):
    run_id: str
    profile_id: str
    model_configuration: LiveModelConfiguration | None = None
    messages: list[LiveMessage] = Field(default_factory=list)
    resume_entries: list[ResumeEntry] = Field(default_factory=list)
    resume_entry_validation_issues: list[ResumeEntryValidationIssue] = Field(default_factory=list)
    resume_entry_trace: list[TraceEvent] = Field(default_factory=list)
    retrieval_results: list[LiveRetrievalResult] = Field(default_factory=list)
    transitions: list[LiveTransition] = Field(default_factory=list)
    cv_results: list[LiveCVResult] = Field(default_factory=list)
    failure: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def reject_sensitive_text(self) -> LiveRunRecord:
        if _contains_sensitive_text(self.model_dump()):
            raise ValueError("live evaluation artifacts must not contain keys or response IDs")
        return self


class LiveScenarioArtifact(StrictModel):
    scenario: str
    runs: list[LiveRunRecord]


def session_to_live_run_record(
    *,
    run_id: str,
    profile_id: str,
    session: Session,
    model_configuration: LiveModelConfiguration | None = None,
    messages: Sequence[LiveMessage] = (),
    transitions: Sequence[LiveTransition] = (),
    cv_results: Sequence[LiveCVResult] | None = None,
    failure: str | None = None,
    note: str | None = None,
) -> LiveRunRecord:
    recorded_cv_results = list(cv_results or [])
    if cv_results is None and session.selected_job_id is not None:
        recorded_cv_results.append(
            LiveCVResult(
                selected_job_id=session.selected_job_id,
                validation_issues=[
                    LiveValidationIssue(code=issue.code, message=issue.message)
                    for issue in session.validation_issues
                ],
                export_outcome=export_outcome(session.state),
            )
        )
    return LiveRunRecord(
        run_id=run_id,
        profile_id=profile_id,
        model_configuration=model_configuration,
        messages=list(messages),
        resume_entries=session.resume_entries,
        resume_entry_validation_issues=session.resume_entry_validation_issues,
        resume_entry_trace=[
            event for event in session.trace
            if event.event_type.startswith(("resume_entry_", "resume_entries_"))
        ],
        retrieval_results=[
            LiveRetrievalResult(
                document_id=result.document_id,
                score=result.score,
                excerpt=result.excerpt,
            )
            for result in session.retrieval_results[:3]
        ],
        transitions=list(transitions),
        cv_results=recorded_cv_results,
        failure=failure,
        note=note,
    )
