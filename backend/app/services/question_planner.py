"""Question planning for the mock interview: planner protocol, offline planner and validation.

The flow service never trusts planner output directly. ``validate_plan`` checks every planned
question against the frozen interview context before an interview can become ``ready``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.interview_models import (
    QUESTION_TEXT_MAX,
    InterviewContextSnapshot,
    PlannedQuestion,
    QuestionCategory,
)
from app.domain.models import ResumeEntry, ResumeEntryKind
from app.providers.base import ProviderUnavailableError
from app.services.retrieval import _requirement_items


class QuestionPlanner(Protocol):
    def plan_questions(
        self, context: InterviewContextSnapshot, *, problems: list[str] | None = None
    ) -> list[PlannedQuestion]:
        """Return planned main questions; ``problems`` lists issues found in a previous attempt."""
        ...


class UnavailableQuestionPlanner:
    """Used when no OpenAI key is configured, so creation fails with a recoverable 503."""

    def plan_questions(
        self, context: InterviewContextSnapshot, *, problems: list[str] | None = None
    ) -> list[PlannedQuestion]:
        del context, problems
        raise ProviderUnavailableError("OPENAI_API_KEY is not configured.")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class PlanValidation:
    questions: list[PlannedQuestion]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def locate_excerpt(excerpt: str, description: str) -> str | None:
    """Return the exact substring of ``description`` that ``excerpt`` refers to, if any.

    An exact match is returned unchanged. Otherwise a whitespace/case-insensitive match is
    mapped back to the original characters, so the stored excerpt is always verbatim.
    """
    candidate = excerpt.strip().strip('"').strip()
    if not candidate:
        return None
    if candidate in description:
        return candidate
    words = [re.escape(word) for word in candidate.split()]
    if not words:
        return None
    pattern = re.compile(r"\s+".join(words), flags=re.IGNORECASE)
    match = pattern.search(description)
    return match.group(0) if match else None


def validate_plan(
    context: InterviewContextSnapshot, planned: list[PlannedQuestion]
) -> PlanValidation:
    expected = context.config.main_question_count
    fact_ids = {fact.fact_id for fact in context.confirmed_facts}
    entry_ids = {entry.entry_id for entry in context.approved_entries}
    problems: list[str] = []
    checked: list[PlannedQuestion] = []
    seen_texts: set[str] = set()

    if len(planned) < expected:
        problems.append(f"Return exactly {expected} questions; received {len(planned)}.")
    for index, question in enumerate(planned[:expected], start=1):
        text = question.text.strip()
        if not text:
            problems.append(f"Question {index} is blank.")
            continue
        key = _normalise(text)
        if key in seen_texts:
            problems.append(f"Question {index} duplicates an earlier question.")
        seen_texts.add(key)
        unknown_facts = sorted(set(question.fact_ids) - fact_ids)
        if unknown_facts:
            problems.append(f"Question {index} cites unknown fact_ids {unknown_facts}.")
        unknown_entries = sorted(set(question.resume_entry_ids) - entry_ids)
        if unknown_entries:
            problems.append(
                f"Question {index} cites unknown resume_entry_ids {unknown_entries}."
            )
        excerpt = question.job_requirement_excerpt
        if excerpt is not None:
            # A paraphrased excerpt cannot be shown as a quotation from the job: drop it.
            excerpt = locate_excerpt(excerpt, context.job.description)
        checked.append(
            question.model_copy(
                update={
                    "text": text,
                    "rationale": question.rationale.strip(),
                    "fact_ids": list(dict.fromkeys(question.fact_ids)),
                    "resume_entry_ids": list(dict.fromkeys(question.resume_entry_ids)),
                    "job_requirement_excerpt": excerpt,
                }
            )
        )

    categories: set[str] = {question.category for question in checked}
    interview_type: str = context.config.interview_type
    if interview_type in {"behavioural", "technical"} and categories - {interview_type}:
        problems.append(
            f"A {interview_type} interview must only contain {interview_type} questions."
        )
    if interview_type == "mixed" and len(checked) >= 2 and len(categories) < 2:
        problems.append("A mixed interview needs both behavioural and technical questions.")
    return PlanValidation(questions=checked, problems=problems)


# ---------------------------------------------------------------------------
# Offline template planner (no model call)
# ---------------------------------------------------------------------------


_SENTENCE_HINTS = re.compile(
    r"\b(experience|skill|knowledge|abilit|familiar|proficien|understanding|requir|build|"
    r"develop|design|work with|use)\w*",
    flags=re.IGNORECASE,
)


_NON_SKILL_REQUIREMENT = re.compile(
    r"\b(degree|bachelor|master|phd|doctorate|years?|qualification|citizen\w*|visa|"
    r"work rights|eligib\w*|licen[cs]e|clearance)\b",
    flags=re.IGNORECASE,
)


def practicable_requirements(description: str) -> list[str]:
    """Requirements a candidate can discuss in an interview (not degrees, years or visas)."""
    return [
        item for item in job_requirements(description) if not _NON_SKILL_REQUIREMENT.search(item)
    ]


def job_requirements(description: str) -> list[str]:
    """Requirement phrases that are exact substrings of the job description."""
    items = [item for item in _requirement_items(description) if item and item in description]
    if items:
        return items
    sentences = [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", description) if s.strip()]
    hinted = [s.rstrip(".;") for s in sentences if _SENTENCE_HINTS.search(s)]
    return [s for s in (hinted or sentences) if s and s in description][:8]


def _short(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) >= 3}


def _entry_name(entry: ResumeEntry) -> str:
    """Short spoken name for an entry, e.g. 'Team Course Planner' from 'Team ...: built ...'."""
    return _short(entry.heading.text.split(": ", 1)[0], 80)


def _entry_text(entry: ResumeEntry) -> str:
    parts = [entry.heading.text, *(bullet.text for bullet in entry.bullets)]
    if entry.organisation_or_context is not None:
        parts.append(entry.organisation_or_context.text)
    return " ".join(parts)


class TemplateQuestionPlanner:
    """Deterministic planner for offline tests and the local demo.

    It only reuses wording from approved entries and the job description, so it cannot invent
    candidate history. It is much less natural than the model planner.
    """

    def plan_questions(
        self, context: InterviewContextSnapshot, *, problems: list[str] | None = None
    ) -> list[PlannedQuestion]:
        del problems
        count = context.config.main_question_count
        job = context.job
        stories = [
            entry
            for entry in context.approved_entries
            if entry.kind
            in {ResumeEntryKind.PROJECT, ResumeEntryKind.EXPERIENCE, ResumeEntryKind.ACHIEVEMENT}
        ]
        behavioural: list[PlannedQuestion] = [
            PlannedQuestion(
                category="behavioural",
                text=_cap(
                    f"Why are you interested in the {_short(job.title, 80)} role, and what do "
                    "you think you would bring to it?"
                ),
                rationale="Opening motivation question based on the target role title.",
            )
        ]
        for entry in stories:
            behavioural.append(
                PlannedQuestion(
                    category="behavioural",
                    text=_cap(
                        f"Tell me about {_entry_name(entry)}. What was your own "
                        "contribution, what challenge did you face, and what was the result?"
                    ),
                    rationale="Asks the candidate to expand an approved resume entry using STAR.",
                    fact_ids=list(entry.source_fact_ids),
                    resume_entry_ids=[entry.entry_id],
                )
            )
        behavioural.extend(
            PlannedQuestion(category="behavioural", text=text, rationale=rationale)
            for text, rationale in (
                (
                    "Describe a time you worked in a team and disagreed about an approach. "
                    "What did you do?",
                    "Generic teamwork question; no candidate history is assumed.",
                ),
                (
                    "Tell me about a time you had to learn a new tool or concept quickly. "
                    "How did you approach it?",
                    "Generic learning question; no candidate history is assumed.",
                ),
            )
        )

        technical: list[PlannedQuestion] = []
        for requirement in practicable_requirements(job.description):
            related = max(
                stories,
                key=lambda entry: len(_tokens(_entry_text(entry)) & _tokens(requirement)),
                default=None,
            )
            overlap = related is not None and bool(
                _tokens(_entry_text(related)) & _tokens(requirement)
            )
            if related is not None and overlap:
                text = (
                    f'This role mentions "{_short(requirement)}". Which parts of '
                    f"{_entry_name(related)} are most relevant to that, and how "
                    "would you build on them here?"
                )
                question = PlannedQuestion(
                    category="technical",
                    text=_cap(text),
                    rationale="Links a job requirement to an approved entry with shared keywords.",
                    fact_ids=list(related.source_fact_ids),
                    resume_entry_ids=[related.entry_id],
                    job_requirement_excerpt=requirement,
                )
            else:
                question = PlannedQuestion(
                    category="technical",
                    text=_cap(
                        f'This role mentions "{_short(requirement)}". How would you approach '
                        "this in practice, and what would you check first?"
                    ),
                    rationale="Probes a job requirement without assuming candidate experience.",
                    job_requirement_excerpt=requirement,
                )
            technical.append(question)
        technical.append(
            PlannedQuestion(
                category="technical",
                text="Walk me through how you would test and debug a feature before releasing it.",
                rationale="Generic engineering-practice question.",
            )
        )

        if context.config.interview_type == "behavioural":
            ordered = behavioural
        elif context.config.interview_type == "technical":
            ordered = technical
        else:
            ordered = _interleave(behavioural, technical)
        return _pad(_unique(ordered), count, context.config.interview_type)


def _cap(text: str) -> str:
    return text if len(text) <= QUESTION_TEXT_MAX else text[: QUESTION_TEXT_MAX - 1] + "…"


def _interleave(
    first: list[PlannedQuestion], second: list[PlannedQuestion]
) -> list[PlannedQuestion]:
    ordered: list[PlannedQuestion] = []
    for index in range(max(len(first), len(second))):
        if index < len(first):
            ordered.append(first[index])
        if index < len(second):
            ordered.append(second[index])
    return ordered


def _unique(questions: list[PlannedQuestion]) -> list[PlannedQuestion]:
    seen: set[str] = set()
    result: list[PlannedQuestion] = []
    for question in questions:
        key = _normalise(question.text)
        if key not in seen:
            seen.add(key)
            result.append(question)
    return result


_PADDING: dict[QuestionCategory, list[str]] = {
    "behavioural": [
        "Tell me about a mistake you made on a project and what you learned from it.",
        "Describe a time you had to manage several deadlines at once.",
        "Tell me about feedback you received and how you acted on it.",
        "Describe a situation where you had to explain your work to someone else.",
        "Tell me about a goal you set for yourself and how you worked towards it.",
    ],
    "technical": [
        "How do you decide how to structure a new piece of code before you start?",
        "Explain a technical concept you know well as if to a non-technical teammate.",
        "How would you investigate a bug that only happens occasionally?",
        "How do you keep code readable and maintainable when working in a team?",
        "What trade-offs would you consider when choosing between two technical approaches?",
    ],
}


def _pad(
    questions: list[PlannedQuestion], count: int, interview_type: str
) -> list[PlannedQuestion]:
    categories: list[QuestionCategory] = (
        ["behavioural"] if interview_type == "behavioural"
        else ["technical"] if interview_type == "technical"
        else ["behavioural", "technical"]
    )
    padded = list(questions)
    pool = [
        (category, text)
        for round_index in range(5)
        for category in categories
        for text in [_PADDING[category][round_index]]
    ]
    for category, text in pool:
        if len(padded) >= count:
            break
        padded = _unique(
            [*padded, PlannedQuestion(category=category, text=text, rationale="Generic question.")]
        )
    return padded[:count]
