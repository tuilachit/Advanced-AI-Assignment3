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
from app.providers.base import ProviderProtocolError, ProviderTurn


class ScriptedProvider:
    """Deterministic provider used by offline tests and local demonstrations."""

    def __init__(self, turns: list[ProviderTurn]) -> None:
        self._turns = list(turns)
        self.seen_tools: list[list[dict[str, Any]]] = []

    def respond(
        self,
        *,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        del input_items
        self.seen_tools.append(tools)
        if not self._turns:
            raise ProviderProtocolError("The scripted provider has no response remaining.")
        return self._turns.pop(0)


class ScriptedCVProvider:
    def __init__(
        self,
        *,
        generated: CVDocument,
        validation_issues: list[ValidationIssue] | None = None,
        proposed_entries: list[ResumeEntry] | None = None,
        entry_validation_issues: list[ResumeEntryValidationIssue] | None = None,
    ) -> None:
        self._generated = generated
        self._validation_issues = validation_issues or []
        self._proposed_entries = proposed_entries or []
        self._entry_validation_issues = entry_validation_issues or []

    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument:
        del contact_facts, approved_entries, job
        return self._generated.model_copy(deep=True)

    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]:
        del confirmed_facts
        return [entry.model_copy(deep=True) for entry in self._proposed_entries]

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]:
        del entries, confirmed_facts
        return [issue.model_copy(deep=True) for issue in self._entry_validation_issues]

    def validate_claims(self, cv: CVDocument, confirmed_facts: list[Fact]) -> list[ValidationIssue]:
        del cv, confirmed_facts
        return [issue.model_copy(deep=True) for issue in self._validation_issues]
