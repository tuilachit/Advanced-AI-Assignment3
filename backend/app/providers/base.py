from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from app.domain.models import (
    CVDocument,
    Fact,
    Job,
    ResumeEntry,
    ResumeEntryValidationIssue,
    StrictModel,
    ValidationIssue,
)


class ProviderError(RuntimeError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderProtocolError(ProviderError):
    pass


class ToolCall(StrictModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ProviderTurn(StrictModel):
    message: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    output_items: list[dict[str, Any]] = Field(default_factory=list)


class AgentModelProvider(Protocol):
    def respond(
        self,
        *,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn: ...


class ResumeEntryProposal(StrictModel):
    entries: list[ResumeEntry]


class ResumeEntryValidationReport(StrictModel):
    issues: list[ResumeEntryValidationIssue]


class ResumeEntryProvider(Protocol):
    def propose_resume_entries(self, confirmed_facts: list[Fact]) -> list[ResumeEntry]: ...

    def validate_resume_entries(
        self, entries: list[ResumeEntry], confirmed_facts: list[Fact]
    ) -> list[ResumeEntryValidationIssue]: ...


class CVProvider(ResumeEntryProvider, Protocol):
    def generate_cv(
        self, contact_facts: list[Fact], approved_entries: list[ResumeEntry], job: Job
    ) -> CVDocument: ...

    def validate_claims(
        self, cv: CVDocument, confirmed_facts: list[Fact]
    ) -> list[ValidationIssue]: ...
