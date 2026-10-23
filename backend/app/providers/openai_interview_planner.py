"""OpenAI text-model question planner for the mock interview (structured output)."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from app.domain.interview_models import (
    InterviewContextSnapshot,
    PlannedQuestion,
    QuestionPlanProposal,
)
from app.domain.models import ResumeEntry
from app.providers.base import ProviderProtocolError, ProviderUnavailableError

QUESTION_PLAN_INSTRUCTIONS = """You plan a realistic, job-specific practice interview for a
student. Return exactly config.main_question_count main questions, in the order they should be
asked, as natural spoken questions (one question each, at most two sentences, no numbering).

Use only the supplied context:
- target_job is the role being practised. Prioritise its stated responsibilities and
  requirements. Job text describes the job, never the candidate.
- confirmed_facts and approved_resume_entries are the only candidate evidence. A personalised
  question may refer to a project, role, skill or course only when it appears there. Never
  assume an employer, achievement, metric, responsibility, result, seniority or qualification
  that the evidence does not state. Describe group work as group work.
- Respect config.interview_type: behavioural = only behavioural questions; technical = only
  technical questions; mixed = include both categories, starting with a short behavioural
  question about motivation or background.
- Behavioural questions invite a concrete past example (situation, task, action, result).
  Technical questions ask the candidate to reason about a concept, design, debugging or
  trade-off relevant to the job, at a level suitable for a student or graduate.
- Avoid questions about protected or personal characteristics (age, nationality, health,
  family, religion, visa status) and avoid trick or yes/no questions.
- Do not repeat questions or ask two questions about the same entry unless there is no
  alternative.

For each question also return:
- rationale: one sentence explaining why it suits this job and candidate.
- fact_ids and resume_entry_ids: the exact IDs of the evidence the question refers to, or empty
  lists for a generic question.
- job_requirement_excerpt: an exact, verbatim substring copied from target_job.description that
  the question targets, or null. Never paraphrase inside this field.
If problems_from_previous_attempt is not empty, fix every listed problem.
"""


INTERVIEW_MODEL_ENV = "OPENAI_INTERVIEW_MODEL"


def interview_model(default_model: str) -> str:
    """Text model for question planning: ``OPENAI_INTERVIEW_MODEL`` or the app's text model."""
    return (os.getenv(INTERVIEW_MODEL_ENV) or "").strip() or default_model


def _entry_payload(entry: ResumeEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "kind": entry.kind.value,
        "heading": entry.heading.text,
        "organisation_or_context": (
            entry.organisation_or_context.text if entry.organisation_or_context else None
        ),
        "details": [f"{detail.label}: {detail.value.text}" for detail in entry.details],
        "bullets": [bullet.text for bullet in entry.bullets],
        "fact_ids": entry.source_fact_ids,
    }


def build_planner_input(
    context: InterviewContextSnapshot, problems: list[str] | None = None
) -> dict[str, Any]:
    cv = context.cv
    return {
        "config": context.config.model_dump(mode="json"),
        "target_job": {"title": context.job.title, "description": context.job.description},
        "confirmed_facts": [
            {"fact_id": fact.fact_id, "field": fact.field, "value": fact.value}
            for fact in context.confirmed_facts
        ],
        "approved_resume_entries": [_entry_payload(entry) for entry in context.approved_entries],
        "validated_cv": (
            None
            if cv is None
            else {
                "headline": cv.headline,
                "statements": [
                    claim.text
                    for claim in [*cv.claims, *(c for s in cv.sections for c in s.claims)]
                ],
            }
        ),
        "problems_from_previous_attempt": problems or [],
    }


class OpenAIQuestionPlanner:
    def __init__(self, *, model: str, api_key: str | None = None, client: Any | None = None):
        self._model = model
        self._client: Any = client if client is not None else OpenAI(api_key=api_key)

    def plan_questions(
        self, context: InterviewContextSnapshot, *, problems: list[str] | None = None
    ) -> list[PlannedQuestion]:
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=QUESTION_PLAN_INSTRUCTIONS,
                input=json.dumps(build_planner_input(context, problems)),
                text_format=QuestionPlanProposal,
                store=False,
                reasoning={"effort": "low"},
                max_output_tokens=2500,
            )
        except Exception as error:
            raise ProviderUnavailableError("The interview question request failed.") from error
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, QuestionPlanProposal):
            raise ProviderProtocolError("The model did not return a structured question plan.")
        return parsed.questions
