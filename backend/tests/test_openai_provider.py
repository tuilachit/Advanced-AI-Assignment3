import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.models import (
    CVClaim,
    CVDocument,
    Fact,
    FactSource,
    FactSourceType,
    FactStatus,
    Job,
    ResumeEntry,
    ResumeEntryKind,
    ResumeText,
    ValidationIssue,
)
from app.providers.openai_provider import (
    AGENT_INSTRUCTIONS,
    CV_VALIDATION_INSTRUCTIONS,
    OpenAIEmbeddingProvider,
    OpenAIModelProvider,
)
from app.services.agent import AGENT_TOOLS


class CapturingResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        function_call = SimpleNamespace(
            type="function_call",
            call_id="call-1",
            name="retrieve_jobs",
            arguments="{}",
            model_dump=lambda **_kwargs: {
                "type": "function_call",
                "call_id": "call-1",
                "name": "retrieve_jobs",
                "arguments": "{}",
            },
        )
        return SimpleNamespace(
            status="completed", incomplete_details=None, output=[function_call], output_text=""
        )


class CapturingEmbeddings:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])]
        )


class CapturingStructuredResponses:
    def __init__(self, parsed: Any) -> None:
        self.parsed = parsed
        self.kwargs: dict[str, Any] = {}
        self.with_raw_response = self

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            http_response=SimpleNamespace(close=lambda: None, json=lambda: {
                "status": "completed", "incomplete_details": None,
            }),
            parse=lambda: SimpleNamespace(output_parsed=self.parsed),
        )


def test_openai_agent_provider_enforces_privacy_and_strict_serial_tools() -> None:
    responses = CapturingResponses()
    client = SimpleNamespace(responses=responses)
    provider = OpenAIModelProvider(client=client, model="gpt-5.6-luna")

    turn = provider.respond(
        input_items=[{"role": "user", "content": "Find jobs"}], tools=AGENT_TOOLS
    )

    assert responses.kwargs["model"] == "gpt-5.6-luna"
    assert responses.kwargs["store"] is False
    assert responses.kwargs["parallel_tool_calls"] is False
    assert all(tool["strict"] is True for tool in responses.kwargs["tools"])
    assert turn.tool_calls[0].name == "retrieve_jobs"
    assert turn.tool_calls[0].arguments == {}


def test_agent_prompt_names_profile_categories_without_inventing_unavailable_facts() -> None:
    assert "contact details" in AGENT_INSTRUCTIONS
    assert "achievements" in AGENT_INSTRUCTIONS
    assert "target role" in AGENT_INSTRUCTIONS
    assert "keep that category absent" in AGENT_INSTRUCTIONS


def test_agent_request_prioritizes_ambiguous_role_before_contact_collection() -> None:
    responses = CapturingResponses()
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    provider.respond(
        input_items=[{"role": "user", "content": "I have not decided my role."}], tools=AGENT_TOOLS
    )
    assert (
        "Clarify an ambiguous target role before asking for name or contact details"
        in responses.kwargs["instructions"]
    )


def test_generation_request_guards_observed_live_overstatement_and_citation_errors() -> None:
    responses = CapturingStructuredResponses(CVDocument(target_job_id="job-1", headline="Python"))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    provider.generate_cv(
        [], [], Job(document_id="job-1", title="Engineer", description="Build APIs.")
    )
    instructions = responses.kwargs["instructions"]
    assert "A listed skill establishes a skill, not experience" in instructions
    assert (
        "Do not call the candidate a graduate unless completed graduation is explicit"
        in instructions
    )
    assert "Cite project or experience facts for backend work in the headline" in instructions


def test_generation_request_preserves_team_ownership_and_professional_identity() -> None:
    responses = CapturingStructuredResponses(CVDocument(target_job_id="job-1", headline="Python"))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    provider.generate_cv(
        [], [], Job(document_id="job-1", title="Engineer", description="Build APIs.")
    )
    instructions = responses.kwargs["instructions"]
    assert "For group projects, describe the candidate's stated contributions" in instructions
    assert (
        "Do not turn skills or a target role into a current professional identity" in instructions
    )


def test_generation_request_requires_material_job_specific_tailoring() -> None:
    responses = CapturingStructuredResponses(CVDocument(target_job_id="job-1", headline="Python"))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    provider.generate_cv(
        [],
        [],
        Job(
            document_id="job-1",
            title="Data Analyst",
            description="Analyse data with Python.",
        ),
    )

    instructions = responses.kwargs["instructions"]
    assert "materially tailor" in instructions
    assert "prioritise the approved entries" in instructions
    assert "do not return a generic cv" in instructions.lower()
    assert "unchanged when the target job changes" in instructions.lower()


def test_generation_request_prioritises_confirmed_entries_for_each_job() -> None:
    responses = CapturingStructuredResponses(CVDocument(target_job_id="job-1", headline="Python"))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    entries = [
        ResumeEntry(
            entry_id="api-project",
            kind=ResumeEntryKind.PROJECT,
            heading=ResumeText(text="Course Planner API", fact_ids=["fact-api"]),
            bullets=[
                ResumeText(
                    text="Implemented Python REST endpoints and SQL queries.",
                    fact_ids=["fact-api"],
                )
            ],
            source_fact_ids=["fact-api"],
        ),
        ResumeEntry(
            entry_id="analytics-project",
            kind=ResumeEntryKind.PROJECT,
            heading=ResumeText(text="Student Services Dashboard", fact_ids=["fact-data"]),
            bullets=[
                ResumeText(
                    text="Cleaned pandas data and built a dashboard for analysis.",
                    fact_ids=["fact-data"],
                )
            ],
            source_fact_ids=["fact-data"],
        ),
    ]

    provider.generate_cv(
        [],
        entries,
        Job(
            document_id="job-api",
            title="Backend Software Engineer",
            description="Build Python services, REST APIs and SQL data access.",
        ),
    )
    api_payload = json.loads(responses.kwargs["input"])

    provider.generate_cv(
        [],
        entries,
        Job(
            document_id="job-data",
            title="Data Analyst",
            description="Analyse datasets with pandas and build dashboards.",
        ),
    )
    data_payload = json.loads(responses.kwargs["input"])

    assert api_payload["targeting"]["priority_entry_ids"] == ["api-project", "analytics-project"]
    assert data_payload["targeting"]["priority_entry_ids"] == ["analytics-project", "api-project"]


def test_openai_embedding_provider_returns_vectors_in_api_order() -> None:
    embeddings = CapturingEmbeddings()
    client = SimpleNamespace(embeddings=embeddings)
    provider = OpenAIEmbeddingProvider(client=client, model="text-embedding-3-small")

    vectors = provider.embed(["first", "second"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert embeddings.kwargs == {
        "model": "text-embedding-3-small",
        "input": ["first", "second"],
        "encoding_format": "float",
    }


def test_openai_provider_generates_structured_cv_without_storing_response() -> None:
    fact = Fact(
        field="project",
        value="Built a Python API",
        status=FactStatus.CONFIRMED,
        source=FactSource(source_type=FactSourceType.USER_MESSAGE, reference="message-1"),
    )
    generated = CVDocument(
        target_job_id="job-1",
        headline="Software Engineering Student",
        claims=[CVClaim(text="Built a Python API.", fact_ids=[fact.fact_id])],
    )
    responses = CapturingStructuredResponses(generated)
    provider = OpenAIModelProvider(
        client=SimpleNamespace(responses=responses), model="gpt-5.6-luna"
    )

    result = provider.generate_cv(
        [],
        [
            ResumeEntry(
                kind=ResumeEntryKind.PROJECT,
                heading=ResumeText(text=fact.value, fact_ids=[fact.fact_id]),
                source_fact_ids=[fact.fact_id],
            )
        ],
        Job(document_id="job-1", title="Software Engineer", description="Build APIs."),
    )

    assert result == generated
    assert responses.kwargs["store"] is False
    assert responses.kwargs["text_format"] is CVDocument
    payload = json.loads(responses.kwargs["input"])
    assert set(payload) == {
        "confirmed_contact_facts",
        "approved_resume_entries",
        "target_job",
        "targeting",
    }
    assert payload["confirmed_contact_facts"] == []
    assert payload["approved_resume_entries"][0]["heading"]["text"] == "Built a Python API"
    assert payload["targeting"]["target_job_title"] == "Software Engineer"


def test_openai_provider_returns_structured_claim_validation_issues() -> None:
    issue = ValidationIssue(
        claim_id="claim-1",
        code="not_entailed",
        message="The claim is not supported.",
    )
    responses = CapturingStructuredResponses(SimpleNamespace(issues=[issue]))
    provider = OpenAIModelProvider(
        client=SimpleNamespace(responses=responses), model="gpt-5.6-luna"
    )
    cv = CVDocument(
        target_job_id="job-1",
        headline="Engineer",
        claims=[CVClaim(claim_id="claim-1", text="Expert.", fact_ids=["fact-1"])],
    )

    issues = provider.validate_claims(cv, [])

    assert issues == [issue]
    assert responses.kwargs["store"] is False
    assert "warning" in CV_VALIDATION_INSTRUCTIONS.lower()
    assert "interpretive" in CV_VALIDATION_INSTRUCTIONS.lower()


def test_semantic_audit_includes_headline_as_an_evidence_linked_claim() -> None:
    responses = CapturingStructuredResponses(SimpleNamespace(issues=[]))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    cv = CVDocument.model_validate(
        {
            "target_job_id": "job-1",
            "headline": "Ten years of engineering",
            "headline_fact_ids": ["fact-name"],
        }
    )
    provider.validate_claims(cv, [])
    payload = json.loads(responses.kwargs["input"])
    assert payload["claims_to_audit"][0] == {
        "claim_id": "headline",
        "text": "Ten years of engineering",
        "fact_ids": ["fact-name"],
    }


def test_openai_entry_proposal_is_structured_private_and_non_embellishing() -> None:
    from app.providers.base import ResumeEntryProposal

    proposal = ResumeEntryProposal(entries=[])
    responses = CapturingStructuredResponses(proposal)
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    fact = Fact(
        field="experience",
        value="Investigated chatbot failures in a team internship",
        status=FactStatus.CONFIRMED,
        source=FactSource(source_type=FactSourceType.USER_MESSAGE, reference="message-1"),
    )
    assert provider.propose_resume_entries([fact]) == []
    assert responses.kwargs["store"] is False
    assert responses.kwargs["text_format"] is ResumeEntryProposal
    assert responses.kwargs["reasoning"] == {"effort": "low"}
    assert json.loads(responses.kwargs["input"]) == {
        "confirmed_facts": [fact.model_dump(mode="json")]
    }
    instructions = responses.kwargs["instructions"]
    for guard in ("metrics", "one-to-three", "group", "skills", "ownership", "qualification"):
        assert guard in instructions


def test_openai_entry_validation_audits_only_cited_confirmed_facts() -> None:
    from app.providers.base import ResumeEntryValidationReport

    responses = CapturingStructuredResponses(ResumeEntryValidationReport(issues=[]))
    provider = OpenAIModelProvider(client=SimpleNamespace(responses=responses), model="offline")
    facts = [
        Fact(
            field="project",
            value="Team API project",
            status=status,
            source=FactSource(source_type=FactSourceType.USER_MESSAGE, reference="m1"),
        )
        for status in (FactStatus.CONFIRMED, FactStatus.CONFIRMED, FactStatus.DRAFT)
    ]
    entry = ResumeEntry(
        kind=ResumeEntryKind.PROJECT,
        heading=ResumeText(text="API project", fact_ids=[facts[0].fact_id]),
        source_fact_ids=[facts[0].fact_id],
    )
    assert provider.validate_resume_entries([entry], facts) == []
    payload = json.loads(responses.kwargs["input"])
    assert payload["confirmed_facts"] == [facts[0].model_dump(mode="json")]
    assert payload["entries_to_audit"] == [entry.model_dump(mode="json")]
    assert responses.kwargs["text_format"] is ResumeEntryValidationReport
    assert responses.kwargs["store"] is False
    assert responses.kwargs["reasoning"] == {"effort": "low"}
    assert "warning" in responses.kwargs["instructions"]
    assert "error" in responses.kwargs["instructions"]


@pytest.mark.parametrize("method", ["propose_resume_entries", "validate_resume_entries"])
@pytest.mark.parametrize("failure", ["malformed", "unavailable"])
def test_entry_provider_failure_is_a_safe_typed_error(method, failure) -> None:
    from app.providers.base import ProviderProtocolError, ProviderUnavailableError

    class Responses(CapturingStructuredResponses):
        def parse(self, **kwargs):
            if failure == "unavailable":
                raise RuntimeError("sensitive provider detail")
            return super().parse(**kwargs)

    provider = OpenAIModelProvider(
        client=SimpleNamespace(responses=Responses(None)), model="offline"
    )
    args = ([],) if method == "propose_resume_entries" else ([], [])
    expected = ProviderProtocolError if failure == "malformed" else ProviderUnavailableError
    with pytest.raises(expected) as caught:
        getattr(provider, method)(*args)
    assert "sensitive" not in str(caught.value)
