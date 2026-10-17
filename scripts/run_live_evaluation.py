#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from app.domain.models import Session, SessionState
from app.domain.workflow import InvalidTransitionError
from app.main import ApplicationServices, build_default_services
from app.providers.base import ProviderError
from app.services.agent import AgentRun, AgentStepLimitError
from app.services.cv import CVEvidenceError
from app.services.live_evaluation import (
    LiveCVResult,
    LiveMessage,
    LiveModelConfiguration,
    LiveRunRecord,
    LiveScenarioArtifact,
    LiveTransition,
    LiveValidationIssue,
    export_outcome,
    profile_to_confirmed_facts,
    session_to_live_run_record,
)
from app.services.resume_entries import ResumeEntryEvidenceError
from app.services.retrieval import ProfileNotConfirmedError
from app.settings import Settings

SCENARIOS = (
    "supplied-five",
    "two-job-comparison",
    "session-isolation",
    "complete-agent",
    "incomplete-agent",
    "unseen",
)
MODEL_CONFIGURATION = LiveModelConfiguration(
    chat_model="gpt-5.6-luna",
    embedding_model="text-embedding-3-small",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPLIED_PROFILES_PATH = PROJECT_ROOT / "data" / "student_profiles.jsonl"
SUPPLIED_INTRODUCTIONS_PATH = PROJECT_ROOT / "data" / "student_introductions.jsonl"
UNSEEN_PROFILE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "04_System_Tests"
    / "test_profiles"
    / "unseen_profile_01.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an approved live-model CV Builder evaluation scenario."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def _artifact_filename(scenario: str) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S%f")
    return f"{timestamp}-{scenario}.json"


def _write_manifest(output_dir: Path, scenario: str, artifact_name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "artifacts": [artifact_name],
                "model_configuration": {
                    "chat_model": "gpt-5.6-luna",
                    "embedding_model": "text-embedding-3-small",
                },
                "status": "planned",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_unseen_profile() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(UNSEEN_PROFILE_PATH.read_text(encoding="utf-8")))


def _transition(
    transitions: list[LiveTransition], before: SessionState, after: SessionState
) -> None:
    if before is not after:
        transitions.append(
            LiveTransition(from_state=before.value, to_state=after.value)
        )


def _handle_agent_message(
    services: ApplicationServices,
    session: Session,
    message: str,
    transitions: list[LiveTransition],
) -> AgentRun:
    before = session.state
    try:
        return services.agent.handle_message(session.session_id, message)
    finally:
        _transition(transitions, before, session.state)


def _import_profile(session: Session, profile: Mapping[str, object], profile_id: str) -> None:
    session.profile.facts = profile_to_confirmed_facts(profile, profile_id)
    session.profile.revision += 1
    session.state = SessionState.PROFILE_CONFIRMED


def _cv_result(session: Session) -> LiveCVResult:
    if session.selected_job_id is None:
        raise InvalidTransitionError("A selected job is required to record a CV result.")
    return LiveCVResult(
        selected_job_id=session.selected_job_id,
        validation_issues=[
            LiveValidationIssue(code=issue.code, message=issue.message)
            for issue in session.validation_issues
        ],
        export_outcome=export_outcome(session.state),
    )


def _run_profile_workflow(
    services: ApplicationServices,
    profile: Mapping[str, object],
    profile_id: str,
    run_id: str,
    *,
    selected_job_ids: Sequence[str] = (),
    selected_job_count: int = 1,
) -> tuple[LiveRunRecord, str]:
    session = services.workflow.create_session()
    transitions: list[LiveTransition] = []
    cv_results: list[LiveCVResult] = []
    failure: str | None = None

    try:
        before = session.state
        _import_profile(session, profile, profile_id)
        _transition(transitions, before, session.state)

        before = session.state
        services.resume_entries.propose(session.session_id)
        _transition(transitions, before, session.state)
        # Synthetic evaluation fixtures explicitly approve each proposal through
        # the same semantic and provenance checks used by interactive review.
        for entry in session.resume_entries:
            before = session.state
            services.resume_entries.approve(session.session_id, entry.entry_id)
            _transition(transitions, before, session.state)

        before = session.state
        services.retrieve_jobs(session.session_id)
        _transition(transitions, before, session.state)

        jobs_to_run = list(selected_job_ids)
        if not jobs_to_run:
            jobs_to_run = [
                result.document_id
                for result in session.retrieval_results[:selected_job_count]
            ]
        retrieved_ids = {result.document_id for result in session.retrieval_results}
        missing_ids = [job_id for job_id in jobs_to_run if job_id not in retrieved_ids]
        if missing_ids:
            raise InvalidTransitionError(
                "Requested comparison job was absent from the live top three.",
                details={"missing_document_ids": missing_ids},
            )

        for job_id in jobs_to_run:
            before = session.state
            services.workflow.select_job(session.session_id, job_id)
            _transition(transitions, before, session.state)

            before = session.state
            cv = services.generate_cv(session.session_id)
            _transition(transitions, before, session.state)

            before = session.state
            services.cv.validate(session.session_id, cv.cv_id)
            _transition(transitions, before, session.state)
            if services.cv.can_export(session.session_id, cv.cv_id):
                before = session.state
                services.cv.record_export(session.session_id, cv.cv_id)
                _transition(transitions, before, session.state)
            cv_results.append(_cv_result(session))
    except (
        CVEvidenceError, ResumeEntryEvidenceError, InvalidTransitionError,
        ProfileNotConfirmedError, ProviderError,
    ) as error:
        failure = f"{type(error).__name__}: {error}"
        if session.selected_job_id is not None:
            cv_results.append(_cv_result(session))

    return (
        session_to_live_run_record(
            run_id=run_id,
            profile_id=profile_id,
            session=session,
            model_configuration=MODEL_CONFIGURATION,
            transitions=transitions,
            cv_results=cv_results,
            failure=failure,
        ),
        session.session_id,
    )


def _profiles_by_id() -> dict[str, dict[str, Any]]:
    return {row["document_id"]: row for row in _load_jsonl(SUPPLIED_PROFILES_PATH)}


def _run_supplied_five(services: ApplicationServices) -> list[LiveRunRecord]:
    profiles = _profiles_by_id()
    return [
        _run_profile_workflow(
            services,
            profiles[profile_id],
            profile_id,
            f"supplied-five-{profile_id}",
        )[0]
        for profile_id in sorted(profiles)
    ]


def _run_two_job_comparison(services: ApplicationServices) -> list[LiveRunRecord]:
    profile_id = "student_profile_01"
    profile = _profiles_by_id()[profile_id]
    record, _session_id = _run_profile_workflow(
        services,
        profile,
        profile_id,
        "two-job-comparison-student-profile-01",
        selected_job_count=2,
    )
    return [record]


def _fact_sources(session: Session) -> set[str]:
    return {fact.source.reference for fact in session.profile.facts}


def _run_session_isolation(services: ApplicationServices) -> list[LiveRunRecord]:
    profiles = _profiles_by_id()
    records_and_sessions = [
        _run_profile_workflow(
            services,
            profiles[profile_id],
            profile_id,
            f"session-isolation-{profile_id}",
        )
        for profile_id in ("student_profile_01", "student_profile_02")
    ]
    records = [item[0] for item in records_and_sessions]
    sessions = [services.workflow.get_session(item[1]) for item in records_and_sessions]
    isolated = all(
        _fact_sources(session) == {profile_id}
        for session, profile_id in zip(
            sessions,
            ("student_profile_01", "student_profile_02"),
            strict=True,
        )
    )
    note = (
        "Isolation verified: each session retained only its imported profile source."
        if isolated
        else "Isolation failure: a session contained another profile source."
    )
    isolation_failure = None if isolated else note
    return [
        record.model_copy(
            update={"note": note, "failure": record.failure or isolation_failure}
        )
        for record in records
    ]


def _complete_profile_message(profile: Mapping[str, object]) -> str:
    return json.dumps(
        profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_follow_up(message: str) -> bool:
    return "?" in message or bool(
        re.search(r"\bplease\s+(?:provide|share|tell)\b", message.lower())
    )


def _run_complete_agent(services: ApplicationServices) -> list[LiveRunRecord]:
    profile = _load_unseen_profile()
    profile_id = str(profile["document_id"])
    session = services.workflow.create_session()
    supplied_message = _complete_profile_message(profile)
    messages = [LiveMessage(role="user", content=supplied_message)]
    transitions: list[LiveTransition] = []
    failure: str | None = None
    try:
        response = _handle_agent_message(
            services, session, supplied_message, transitions
        )
        messages.append(LiveMessage(role="assistant", content=response.message))
        if _is_follow_up(response.message):
            failure = "Complete profile received a follow-up question; review required."
    except (AgentStepLimitError, ProviderError) as error:
        failure = f"{type(error).__name__}: {error}"
    return [
        session_to_live_run_record(
            run_id="complete-agent-unseen-profile-01",
            profile_id=profile_id,
            session=session,
            model_configuration=MODEL_CONFIGURATION,
            messages=messages,
            transitions=transitions,
            failure=failure,
        )
    ]


def _factual_reply(
    profile: Mapping[str, object], question: str, turn_index: int
) -> str:
    normalized = question.lower()
    if "name" in normalized:
        reply = (
            f"My supplied name is {profile['name']}."
            if profile.get("name")
            else "No name is supplied in this synthetic profile."
        )
        if any(term in normalized for term in ("contact", "email", "phone")):
            reply += " No contact details are supplied in this synthetic profile."
        return reply
    if any(term in normalized for term in ("contact", "email", "phone")):
        return "No contact details are supplied in this synthetic profile."
    target_roles = profile.get("target_roles")
    if any(term in normalized for term in ("role", "target")) and isinstance(
        target_roles, Sequence
    ) and not isinstance(target_roles, str):
        return f"My target role is {target_roles[0]}."
    if any(term in normalized for term in ("degree", "education", "study")):
        return f"My supplied degree is {profile['degree']}."
    projects = profile.get("projects")
    if "project" in normalized and isinstance(projects, Sequence) and not isinstance(
        projects, str
    ) and projects:
        return "The supplied project record is: " + json.dumps(
            projects[0],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if any(term in normalized for term in ("skill", "technology", "technical")):
        skills = profile.get("technical_skills")
        if isinstance(skills, Sequence) and not isinstance(skills, str):
            return "My supplied technical skills are " + ", ".join(map(str, skills)) + "."
    if any(term in normalized for term in ("experience", "employment", "work")):
        experience = profile.get("experience")
        if isinstance(experience, Sequence) and not isinstance(experience, str) and experience:
            return "The supplied experience record is: " + json.dumps(
                experience[0],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        return "No experience record is supplied in this synthetic profile."
    if any(term in normalized for term in ("achievement", "award")):
        return "No verified achievement is supplied in this synthetic profile."
    if turn_index > 0 and isinstance(projects, Sequence) and not isinstance(
        projects, str
    ) and projects:
        return "The supplied project record is: " + json.dumps(
            projects[0],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if isinstance(target_roles, Sequence) and not isinstance(target_roles, str):
        return f"My target role is {target_roles[0]}."
    return "No additional fact for that category is supplied in this synthetic profile."


def _run_incomplete_agent(services: ApplicationServices) -> list[LiveRunRecord]:
    profile_id = "student_profile_04"
    profile = _profiles_by_id()[profile_id]
    introductions = {
        row["document_id"]: row for row in _load_jsonl(SUPPLIED_INTRODUCTIONS_PATH)
    }
    introduction = str(introductions[profile_id]["initial_introduction"])
    session = services.workflow.create_session()
    messages = [LiveMessage(role="user", content=introduction)]
    transitions: list[LiveTransition] = []
    failure: str | None = None
    current_message = introduction
    try:
        for turn_index in range(2):
            response = _handle_agent_message(
                services, session, current_message, transitions
            )
            messages.append(LiveMessage(role="assistant", content=response.message))
            if not _is_follow_up(response.message):
                failure = (
                    "Incomplete profile did not receive two follow-up questions; review required."
                )
                break
            current_message = _factual_reply(profile, response.message, turn_index)
            messages.append(LiveMessage(role="user", content=current_message))
        if failure is None:
            response = _handle_agent_message(
                services, session, current_message, transitions
            )
            messages.append(LiveMessage(role="assistant", content=response.message))
    except (AgentStepLimitError, ProviderError) as error:
        failure = f"{type(error).__name__}: {error}"
    questions = [
        " ".join(message.content.lower().split())
        for message in messages
        if message.role == "assistant" and _is_follow_up(message.content)
    ]
    if failure is None and len(questions) != len(set(questions)):
        failure = "Incomplete profile received a repeated follow-up question; review required."
    return [
        session_to_live_run_record(
            run_id="incomplete-agent-student-profile-04",
            profile_id=profile_id,
            session=session,
            model_configuration=MODEL_CONFIGURATION,
            messages=messages,
            transitions=transitions,
            failure=failure,
        )
    ]


def _run_unseen(services: ApplicationServices) -> list[LiveRunRecord]:
    profile = _load_unseen_profile()
    profile_id = str(profile["document_id"])
    record, _session_id = _run_profile_workflow(
        services,
        profile,
        profile_id,
        "unseen-unseen-profile-01",
    )
    return [record]


SCENARIO_RUNNERS: dict[
    str, Callable[[ApplicationServices], list[LiveRunRecord]]
] = {
    "supplied-five": _run_supplied_five,
    "two-job-comparison": _run_two_job_comparison,
    "session-isolation": _run_session_isolation,
    "complete-agent": _run_complete_agent,
    "incomplete-agent": _run_incomplete_agent,
    "unseen": _run_unseen,
}


def _write_artifact(
    output_dir: Path,
    artifact_name: str,
    scenario: str,
    records: list[LiveRunRecord],
) -> Path:
    artifact = LiveScenarioArtifact(scenario=scenario, runs=records)
    artifact_path = output_dir / artifact_name
    artifact_path.write_text(
        artifact.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_path


def _build_live_services() -> ApplicationServices:
    settings = Settings.from_environment()
    settings.openai_model = MODEL_CONFIGURATION.chat_model
    settings.openai_embedding_model = MODEL_CONFIGURATION.embedding_model
    return build_default_services(settings)


def main(
    argv: Sequence[str] | None = None,
    *,
    services_factory: Callable[[], ApplicationServices] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    artifact_name = _artifact_filename(args.scenario)
    _write_manifest(args.output_dir, args.scenario, artifact_name)
    services = (services_factory or _build_live_services)()
    records = SCENARIO_RUNNERS[args.scenario](services)
    _write_artifact(args.output_dir, artifact_name, args.scenario, records)
    return int(any(record.failure is not None for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
