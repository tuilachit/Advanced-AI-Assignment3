"""Shared helpers for the interview-flow scripts (evaluation and text-mode practice).

They prepare a session from a synthetic profile in ``data/student_profiles.jsonl`` without any
model call: profile fields become confirmed facts, and each substantive fact becomes one
approved resume entry with an exact citation. This exercises the interview flow on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.models import FactInput, ResumeEntry, ResumeEntryKind, ResumeText
from app.domain.workflow import SessionWorkflow
from app.providers.openai_interview_planner import OpenAIQuestionPlanner, interview_model
from app.services.question_planner import QuestionPlanner, TemplateQuestionPlanner
from app.services.retrieval import JobRepository
from app.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = PROJECT_ROOT / "data" / "student_profiles.jsonl"


def load_profiles() -> list[dict[str, Any]]:
    with PROFILES_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_jobs() -> list[Any]:
    return JobRepository.load(JobRepository.default_data_path())


def profile_facts(profile: dict[str, Any]) -> list[FactInput]:
    facts = [FactInput(field="name", value=profile["name"])]
    education = f"{profile['degree']}, {profile['institution']}"
    if profile.get("year"):
        education += f" ({profile['year']})"
    facts.append(FactInput(field="education", value=education))
    if skills := profile.get("technical_skills"):
        facts.append(FactInput(field="skills", value=", ".join(skills)))
    for index, project in enumerate(profile.get("projects") or [], start=1):
        value = f"{project['title']}: {project['description']}"
        facts.append(FactInput(field="project" if index == 1 else f"project_{index}", value=value))
    for index, role in enumerate(profile.get("experience") or [], start=1):
        value = f"{role['role']}, {role.get('organisation', '')}: {role.get('description', '')}"
        field = "experience" if index == 1 else f"experience_{index}"
        facts.append(FactInput(field=field, value=value))
    if roles := profile.get("target_roles"):
        facts.append(FactInput(field="target_role", value=str(roles[0])))
    return [FactInput(field=f.field, value=f.value[:3900]) for f in facts]


def _kind(field: str) -> ResumeEntryKind | None:
    if field == "education":
        return ResumeEntryKind.EDUCATION
    if field == "skills":
        return ResumeEntryKind.SKILLS
    if field.startswith("project"):
        return ResumeEntryKind.PROJECT
    if field.startswith("experience"):
        return ResumeEntryKind.EXPERIENCE
    return None


def prepare_session(workflow: SessionWorkflow, profile: dict[str, Any]) -> str:
    """Create a session with confirmed facts and approved resume entries for ``profile``."""
    session = workflow.create_session()
    session_id = session.session_id
    workflow.update_profile(
        session_id, profile_facts(profile), source_reference=profile["document_id"]
    )
    session = workflow.confirm_profile(session_id)
    entries: list[ResumeEntry] = []
    for fact in session.profile.facts:
        kind = _kind(fact.field)
        if kind is None:
            continue
        heading, _, body = fact.value.partition(": ")
        if kind in {ResumeEntryKind.EDUCATION, ResumeEntryKind.SKILLS} or not body:
            heading, body = fact.value, ""
        ids = [fact.fact_id]
        entries.append(
            ResumeEntry(
                kind=kind,
                heading=ResumeText(text=heading[:1000], fact_ids=ids),
                bullets=[ResumeText(text=body[:1000], fact_ids=ids)] if body else [],
                source_fact_ids=ids,
            )
        )
    session = workflow.set_resume_entries(session_id, entries)
    for entry in session.resume_entries:
        workflow.approve_resume_entry(session_id, entry.entry_id, [])
    return session_id


def make_planner(kind: str) -> QuestionPlanner:
    """``template`` (offline, no key) or ``openai`` (needs OPENAI_API_KEY in .env.local)."""
    if kind == "template":
        return TemplateQuestionPlanner()
    settings = Settings.from_environment()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set (.env.local). Use --planner template.")
    return OpenAIQuestionPlanner(
        model=interview_model(settings.openai_model), api_key=settings.openai_api_key
    )


__all__ = [
    "load_jobs",
    "load_profiles",
    "make_planner",
    "prepare_session",
    "profile_facts",
]
