from __future__ import annotations

from typing import Any

from app.domain.models import (
    CVDocument,
    Fact,
    Job,
    ResumeEntry,
    ResumeEntryValidationIssue,
    ValidationIssue,
)
from app.providers.base import ProviderTurn, ProviderUnavailableError


class MissingOpenAIProvider:
    def _raise(self) -> None:
        raise ProviderUnavailableError(
            "OpenAI is not configured. Add OPENAI_API_KEY to the project .env.local file."
        )

    def respond(
        self,
        *,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        del input_items, tools
        self._raise()
        raise AssertionError("unreachable")

    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument:
        del contact_facts, approved_entries, job
        self._raise()
        raise AssertionError("unreachable")

    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        del confirmed_facts
        self._raise()
        raise AssertionError("unreachable")

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]:
        del entries, confirmed_facts
        self._raise()
        raise AssertionError("unreachable")

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        del cv, confirmed_facts
        self._raise()
        raise AssertionError("unreachable")

    def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        self._raise()
        raise AssertionError("unreachable")
