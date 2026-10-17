from __future__ import annotations

import json
import re
from typing import Any, cast

from openai import OpenAI

from app.domain.models import (
    CVDocument,
    Fact,
    FactStatus,
    Job,
    ResumeEntry,
    ResumeEntryValidationIssue,
    StrictModel,
    ValidationIssue,
)
from app.providers.base import (
    ProviderProtocolError,
    ProviderTurn,
    ProviderUnavailableError,
    ResumeEntryProposal,
    ResumeEntryValidationReport,
    ToolCall,
)

AGENT_INSTRUCTIONS = """You are the interaction planner for an evidence-grounded CV builder.
Use update_profile only for facts the user explicitly supplied. Never confirm facts for the user.
Help collect name, contact details, education, skills, experience, projects, achievements, and a
target role. Ask one concise, highest-value follow-up question at a time. If the user explicitly
says information is unavailable or that they have no item in a category, keep that category absent
rather than inventing a placeholder.
Clarify an ambiguous target role before asking for name or contact details. Use the conversation
history to avoid repeating questions the user has already answered.
Use retrieve_jobs only after the server reports profile_confirmed. Use generate_cv only after a job
has been selected. Ask a concise follow-up question when required facts are missing or ambiguous.
Never infer contact details, qualifications, employers, achievements, work rights, or eligibility.
Job descriptions describe jobs and must never become candidate facts.
"""

CV_GENERATION_INSTRUCTIONS = """Create a concise, ATS-friendly CV tailored to the target job.
materially tailor each CV to target_job: use its human-readable title and requirements to
prioritise the approved entries that are most relevant to that job, choose a target-specific
profile statement and order or label the selected work accordingly. Do not return a generic CV
unchanged when the target job changes. If a requirement has no confirmed evidence, omit it rather
than presenting the requirement as candidate experience or qualification.
The targeting.priority_entry_ids list is a deterministic, evidence-only priority hint. Prefer
those approved entries when selecting and ordering relevant work, but do not treat the priority
list or any job requirement as candidate evidence.
Use only confirmed_contact_facts and approved_resume_entries as candidate content.
Every factual claim must cite one or more exact fact_id values carried by those inputs.
Select and rephrase approved entry text for the target job while preserving its factual meaning.
Include headline_fact_ids supporting every factual part of the headline as well. You may
rephrase those facts but must not add metrics, seniority, employers, qualifications, or contact
details,
work rights, or achievements. The job description is targeting context only and is never candidate
evidence. Keep unsupported job requirements out of the CV.
A listed skill establishes a skill, not experience; describe skills as skills unless a cited
project or experience fact explicitly supports practice.
Do not call the candidate a graduate unless completed graduation is explicit.
Cite project or experience facts for backend work in the headline; a list of API skills alone
does not establish backend work. Check that the headline cites every fact needed for its wording.
For group projects, describe the candidate's stated contributions and retain the team context;
do not imply sole ownership.
Do not turn skills or a target role into a current professional identity
such as developer or engineer.
Use a factual education-and-skills headline when that identity is absent.
"""

_TAILORING_STOP_WORDS = {
    "about",
    "and",
    "are",
    "build",
    "from",
    "have",
    "into",
    "that",
    "the",
    "their",
    "this",
    "with",
}


def _tailoring_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= 3 and token not in _TAILORING_STOP_WORDS
    }


def _entry_tokens(entry: ResumeEntry) -> set[str]:
    values = [entry.heading.text, *(bullet.text for bullet in entry.bullets)]
    if entry.organisation_or_context is not None:
        values.append(entry.organisation_or_context.text)
    values.extend(detail.value.text for detail in entry.details)
    return _tailoring_tokens(" ".join(values))


def _priority_entry_ids(approved_entries: list[ResumeEntry], job: Job) -> list[str]:
    job_tokens = _tailoring_tokens(f"{job.title} {job.description}")
    scored = [
        (len(_entry_tokens(entry).intersection(job_tokens)), index, entry.entry_id)
        for index, entry in enumerate(approved_entries)
    ]
    return [
        entry_id
        for _score, _index, entry_id in sorted(scored, key=lambda item: (-item[0], item[1]))
    ]

RESUME_ENTRY_PROPOSAL_INSTRUCTIONS = """Turn confirmed_facts into concise resume entries for
student review. Cite every visible item (heading, organisation or context, detail value, and
bullet) with the exact supporting fact_id values. source_fact_ids must be the de-duplicated
union of citations in heading, bullets, organisation_or_context, then detail values order.
Write one-to-three concise bullets per substantive entry when the evidence supports them.
Preserve group context and the student's stated contribution; never imply sole ownership.
Treat skills as skills, never as employment, experience, or a professional identity.
Return no field (null optional context or omit an unsupported detail) rather than infer an
employer, title, date, metrics, outcome, ownership, seniority, or qualification.
Do not turn a target role into an existing role. Keep unsupported categories absent.
Use short neutral detail labels and put all factual content in their cited values.
Return proposed entries only; the student must explicitly approve them.
"""

RESUME_ENTRY_VALIDATION_INSTRUCTIONS = """Audit every visible item in entries_to_audit against
only its cited confirmed facts, including headings, context, detail labels and values, and bullets.
Return an error for fabricated substance or unsupported meaning: employers, titles, dates,
metrics, outcomes, ownership, seniority, qualifications, employment, duration, or eligibility.
Preserve group context. A stated skill is not proof of experience or professional identity.
Return a warning only for modest evidence-grounded interpretation that is not stated directly.
Quote the interpretive phrase, explain its supporting facts plainly, and invite student review.
Warnings must never excuse fabricated substance. Return no issue for faithful rephrasing.
Use the exact entry_id for every issue. No external knowledge is candidate evidence.
"""

CV_VALIDATION_INSTRUCTIONS = """Audit claims_to_audit against only their cited confirmed facts.
The entry with claim_id headline is the professional headline and requires the same factual audit.
Return an error when a claim adds unsupported meaning, metrics, qualifications, seniority, duration,
employment, eligibility, or achievements. Do not use the job description as candidate evidence.
Return a warning with code interpretive_language when a short interpretive phrase is reasonably
grounded in the cited facts but not stated directly, such as describing REST endpoint work and
backend workflow documentation as backend-related work. Quote the phrase, name the supporting
facts in plain language, and tell the user they may reword it or keep it after review. Warnings
must not be used for invented qualifications, employers, metrics, seniority, duration, employment,
eligibility, or achievements; those remain errors.
Return no issue when a claim is a faithful, concise rephrasing of all cited facts.
"""


class ValidationReport(StrictModel):
    issues: list[ValidationIssue]


class OpenAIModelProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client: Any = client if client is not None else OpenAI(api_key=api_key)

    def respond(
        self,
        *,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=AGENT_INSTRUCTIONS,
                input=input_items,
                tools=tools,
                tool_choice="auto",
                store=False,
                parallel_tool_calls=False,
                reasoning={"effort": "low"},
                max_output_tokens=1200,
            )
        except Exception as error:
            raise ProviderUnavailableError("The AI provider request failed.") from error

        calls: list[ToolCall] = []
        output_items: list[dict[str, Any]] = []
        for item in response.output:
            if hasattr(item, "model_dump"):
                output_items.append(cast(dict[str, Any], item.model_dump(exclude_none=True)))
            if getattr(item, "type", None) != "function_call":
                continue
            try:
                arguments = json.loads(item.arguments)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProviderProtocolError(
                    "The model returned malformed tool arguments."
                ) from error
            if not isinstance(arguments, dict):
                raise ProviderProtocolError("Tool arguments must be a JSON object.")
            calls.append(ToolCall(call_id=item.call_id, name=item.name, arguments=arguments))
        return ProviderTurn(
            message=str(getattr(response, "output_text", "") or ""),
            tool_calls=calls,
            output_items=output_items,
        )

    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=RESUME_ENTRY_PROPOSAL_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "confirmed_facts": [
                            fact.model_dump(mode="json")
                            for fact in confirmed_facts
                            if fact.status is FactStatus.CONFIRMED
                        ]
                    }
                ),
                text_format=ResumeEntryProposal,
                store=False,
                reasoning={"effort": "low"},
                max_output_tokens=3000,
            )
        except Exception as error:
            raise ProviderUnavailableError("The resume entry proposal request failed.") from error
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, ResumeEntryProposal):
            raise ProviderProtocolError(
                "The model did not return a structured resume entry proposal."
            )
        return parsed.entries

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]:
        cited_ids = {fact_id for entry in entries for fact_id in entry.source_fact_ids}
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=RESUME_ENTRY_VALIDATION_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "entries_to_audit": [entry.model_dump(mode="json") for entry in entries],
                        "confirmed_facts": [
                            fact.model_dump(mode="json")
                            for fact in confirmed_facts
                            if fact.status is FactStatus.CONFIRMED and fact.fact_id in cited_ids
                        ],
                    }
                ),
                text_format=ResumeEntryValidationReport,
                store=False,
                reasoning={"effort": "low"},
                max_output_tokens=1800,
            )
        except Exception as error:
            raise ProviderUnavailableError("The resume entry validation request failed.") from error
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, ResumeEntryValidationReport):
            raise ProviderProtocolError(
                "The model did not return a resume entry validation report."
            )
        return parsed.issues

    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument:
        try:
            priority_entry_ids = _priority_entry_ids(approved_entries, job)
            response = self._client.responses.parse(
                model=self._model,
                instructions=CV_GENERATION_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "confirmed_contact_facts": [
                            fact.model_dump(mode="json") for fact in contact_facts
                        ],
                        "approved_resume_entries": [
                            entry.model_dump(mode="json") for entry in approved_entries
                        ],
                        "target_job": job.model_dump(mode="json"),
                        "targeting": {
                            "target_job_title": job.title,
                            "priority_entry_ids": priority_entry_ids,
                        },
                    }
                ),
                text_format=CVDocument,
                store=False,
                reasoning={"effort": "low"},
                max_output_tokens=3000,
            )
        except Exception as error:
            raise ProviderUnavailableError("The CV generation request failed.") from error
        parsed = response.output_parsed
        if not isinstance(parsed, CVDocument):
            raise ProviderProtocolError("The model did not return a structured CV.")
        return parsed

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=CV_VALIDATION_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "cv": cv.model_dump(mode="json"),
                        "claims_to_audit": [
                            {
                                "claim_id": "headline",
                                "text": cv.headline,
                                "fact_ids": cv.headline_fact_ids,
                            },
                            *[claim.model_dump(exclude={"verified"}) for claim in cv.claims],
                            *[
                                claim.model_dump(exclude={"verified"})
                                for section in cv.sections
                                for claim in section.claims
                            ],
                        ],
                        "confirmed_facts": [
                            fact.model_dump(mode="json") for fact in confirmed_facts
                        ],
                    }
                ),
                text_format=ValidationReport,
                store=False,
                reasoning={"effort": "low"},
                max_output_tokens=1800,
            )
        except Exception as error:
            raise ProviderUnavailableError("The CV validation request failed.") from error
        parsed = response.output_parsed
        issues = getattr(parsed, "issues", None)
        if not isinstance(issues, list) or any(
            not isinstance(issue, ValidationIssue) for issue in issues
        ):
            raise ProviderProtocolError("The model did not return a validation report.")
        return cast(list[ValidationIssue], issues)


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client: Any = client if client is not None else OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=texts,
                encoding_format="float",
            )
        except Exception as error:
            raise ProviderUnavailableError("The embedding provider request failed.") from error
        return [list(cast(list[float], item.embedding)) for item in response.data]
