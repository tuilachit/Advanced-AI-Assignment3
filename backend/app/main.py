from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import Field, field_validator

from app.api.interview_feedback import build_feedback_router
from app.api.interviews import build_interview_router, register_interview_error_handlers
from app.domain.api_errors import ApiErrorBody, ApiErrorDetail
from app.domain.models import (
    AgentObservation,
    CVDocument,
    FactInput,
    FactSourceType,
    Job,
    ResumeEntryEdit,
    Session,
    StrictModel,
    TraceEvent,
)
from app.domain.workflow import (
    InvalidTransitionError,
    ResumeEntryNotFoundError,
    SessionNotFoundError,
    SessionWorkflow,
)
from app.providers.base import (
    AgentModelProvider,
    ProviderError,
)
from app.providers.interview_feedback import (
    OpenAIInterviewFeedbackProvider,
    UnavailableInterviewFeedbackProvider,
)
from app.providers.openai_interview_planner import OpenAIQuestionPlanner, interview_model
from app.providers.openai_provider import OpenAIEmbeddingProvider, OpenAIModelProvider
from app.providers.unavailable import MissingOpenAIProvider
from app.services.agent import AgentService, AgentStepLimitError
from app.services.cv import CVEvidenceError, CVService
from app.services.feedback_runtime import FeedbackRuntime
from app.services.interview_feedback import InterviewFeedbackService
from app.services.interview_flow import InterviewFlowService
from app.services.question_planner import (
    QuestionPlanner,
    TemplateQuestionPlanner,
    UnavailableQuestionPlanner,
)
from app.services.resume_entries import ResumeEntryEvidenceError, ResumeEntryService
from app.services.retrieval import (
    JobRepository,
    ProfileNotConfirmedError,
    RetrievalService,
)
from app.settings import Settings


class MessageRequest(StrictModel):
    message: str = Field(min_length=1, max_length=8000)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned


class ProfileUpdateRequest(StrictModel):
    facts: list[FactInput] = Field(min_length=1, max_length=30)


class MessageResponse(StrictModel):
    message: str
    observations: list[AgentObservation]
    session: Session


class TraceResponse(StrictModel):
    events: list[TraceEvent]


class CVGenerationResponse(StrictModel):
    cv: CVDocument
    session: Session


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ApiErrorBody, "description": description}
    for code, description in {
        404: "Session or resource not found",
        409: "Workflow state conflict",
        422: "Request or evidence validation error",
        502: "Agent step limit reached",
        503: "AI provider unavailable",
    }.items()
}


@dataclass
class ApplicationServices:
    workflow: SessionWorkflow
    jobs: list[Job]
    retrieval: RetrievalService
    cv: CVService
    resume_entries: ResumeEntryService
    agent_provider: AgentModelProvider
    # A3 interview flow. Offline callers (tests, demo) default to the template planner.
    question_planner: QuestionPlanner | None = None
    agent: AgentService = field(init=False)
    interviews: InterviewFlowService = field(init=False)
    _jobs_by_id: dict[str, Job] = field(init=False)

    def __post_init__(self) -> None:
        self._jobs_by_id = {job.document_id: job for job in self.jobs}
        self.interviews = InterviewFlowService(
            self.workflow,
            self.jobs,
            self.question_planner or TemplateQuestionPlanner(),
        )
        self.agent = AgentService(
            self.workflow,
            self.agent_provider,
            retrieve_jobs=self._retrieve_tool,
            generate_cv=self._generate_tool,
        )

    def retrieve_jobs(self, session_id: str) -> Session:
        session = self.workflow.ensure_can_retrieve_jobs(session_id)
        results = self.retrieval.retrieve(session.profile)
        return self.workflow.set_retrieval_results(session_id, results)

    def generate_cv(self, session_id: str) -> CVDocument:
        session = self.workflow.get_session(session_id)
        if not session.selected_job_id:
            raise InvalidTransitionError("Select a retrieved job before generating a CV.")
        try:
            job = self._jobs_by_id[session.selected_job_id]
        except KeyError as error:
            raise InvalidTransitionError("The selected job no longer exists.") from error
        return self.cv.generate(session_id, job)

    def _retrieve_tool(self, session_id: str) -> dict[str, object]:
        session = self.retrieve_jobs(session_id)
        return {
            "results": [result.model_dump(mode="json") for result in session.retrieval_results],
            "state": session.state.value,
        }

    def _generate_tool(self, session_id: str) -> dict[str, object]:
        cv = self.generate_cv(session_id)
        return {"cv": cv.model_dump(mode="json"), "state": "cv_draft"}


def build_default_services(
    settings: Settings | None = None, *, client: Any | None = None
) -> ApplicationServices:
    selected = settings or Settings.from_environment()
    workflow = SessionWorkflow()
    jobs = JobRepository.load(JobRepository.default_data_path())
    if selected.openai_api_key:
        model_provider: Any = OpenAIModelProvider(
            model=selected.openai_model,
            api_key=selected.openai_api_key,
            client=client,
        )
        embedding_provider: Any = OpenAIEmbeddingProvider(
            model=selected.openai_embedding_model,
            api_key=selected.openai_api_key,
            client=client,
        )
        question_planner: QuestionPlanner = OpenAIQuestionPlanner(
            model=interview_model(selected.openai_model),
            api_key=selected.openai_api_key,
            client=client,
        )
    else:
        model_provider = MissingOpenAIProvider()
        embedding_provider = model_provider
        question_planner = UnavailableQuestionPlanner()
    cv_service = CVService(workflow, model_provider)
    return ApplicationServices(
        workflow=workflow,
        jobs=jobs,
        retrieval=RetrievalService(jobs, embedding_provider),
        cv=cv_service,
        resume_entries=ResumeEntryService(workflow, model_provider),
        agent_provider=model_provider,
        question_planner=question_planner,
    )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ApiErrorBody(error=ApiErrorDetail(code=code, message=message, details=details or {}))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


class _InterviewServiceProxy:
    """Resolve the application flow after startup without constructing SDK resources."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def __getattr__(self, name: str) -> Any:
        return getattr(self._app.state.services.interviews, name)


def create_app(
    services: ApplicationServices | None = None,
    *,
    feedback_service: InterviewFeedbackService | None = None,
) -> FastAPI:
    # Offline construction makes imports and OpenAPI export independent of credentials.
    active = services or build_default_services(Settings())
    feedback = feedback_service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        nonlocal active, feedback
        client: Any | None = None
        runner: FeedbackRuntime | None = None
        try:
            selected = Settings() if services is not None else Settings.from_environment()
            if services is None:
                if selected.openai_api_key:
                    client = OpenAI(api_key=selected.openai_api_key, timeout=30.0, max_retries=0)
                active = build_default_services(selected, client=client)
            application.state.services = active
            if feedback_service is None:
                runner = FeedbackRuntime()
                provider = (
                    OpenAIInterviewFeedbackProvider(model=selected.openai_model, client=client)
                    if client is not None
                    else UnavailableInterviewFeedbackProvider()
                )
                feedback = InterviewFeedbackService(active.interviews, provider, runner=runner)
            application.state.feedback_service = feedback
            yield
        finally:
            try:
                if runner is not None:
                    runner.shutdown()
            finally:
                if client is not None:
                    client.close()

    app = FastAPI(
        title="Evidence CV API",
        version="0.1.0",
        responses=ERROR_RESPONSES,
        lifespan=lifespan,
    )
    app.state.services = active
    app.state.feedback_service = feedback

    def get_feedback_service() -> InterviewFeedbackService:
        if app.state.feedback_service is None:
            raise ProviderError("Feedback runtime has not started.")
        return cast(InterviewFeedbackService, app.state.feedback_service)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    register_interview_error_handlers(app)
    interview_flow = (
        active.interviews
        if services is not None
        else cast(InterviewFlowService, _InterviewServiceProxy(app))
    )
    app.include_router(build_interview_router(interview_flow))
    app.include_router(build_feedback_router(get_feedback_service))

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found(_request: Request, _error: SessionNotFoundError) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "session_not_found",
            "The requested session was not found.",
        )

    @app.exception_handler(ResumeEntryNotFoundError)
    async def resume_entry_not_found(
        _request: Request, _error: ResumeEntryNotFoundError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "resume_entry_not_found",
            "The requested resume entry was not found.",
        )

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition(_request: Request, error: InvalidTransitionError) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            str(error),
            error.details,
        )

    @app.exception_handler(ProfileNotConfirmedError)
    async def profile_not_confirmed(
        _request: Request, error: ProfileNotConfirmedError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            str(error),
        )

    @app.exception_handler(CVEvidenceError)
    async def evidence_error(_request: Request, error: CVEvidenceError) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "cv_evidence_error",
            str(error),
        )

    @app.exception_handler(ResumeEntryEvidenceError)
    async def resume_entry_evidence_error(
        _request: Request, error: ResumeEntryEvidenceError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "resume_entry_evidence_error",
            str(error),
        )

    @app.exception_handler(ProviderError)
    async def provider_error(_request: Request, _error: ProviderError) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "provider_unavailable",
            "The AI provider is unavailable. Check the local configuration and try again.",
        )

    @app.exception_handler(AgentStepLimitError)
    async def step_limit(_request: Request, error: AgentStepLimitError) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "agent_step_limit",
            str(error),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(_request: Request, error: RequestValidationError) -> JSONResponse:
        details = {
            "issues": [
                {key: issue[key] for key in ("type", "loc", "msg", "input") if key in issue}
                for issue in error.errors()
            ]
        }
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "request_validation_error",
            "The request contains invalid data.",
            details,
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/sessions", response_model=Session, status_code=status.HTTP_201_CREATED)
    def create_session() -> Session:
        return active.workflow.create_session()

    @app.get("/api/sessions/{session_id}", response_model=Session)
    def get_session(session_id: str) -> Session:
        return active.workflow.get_session(session_id)

    @app.post("/api/sessions/{session_id}/messages", response_model=MessageResponse)
    def send_message(session_id: str, request: MessageRequest) -> MessageResponse:
        result = active.agent.handle_message(session_id, request.message)
        return MessageResponse(
            message=result.message,
            observations=result.observations,
            session=active.workflow.get_session(session_id),
        )

    @app.put("/api/sessions/{session_id}/profile", response_model=Session)
    def update_profile(session_id: str, request: ProfileUpdateRequest) -> Session:
        return active.workflow.update_profile(
            session_id,
            request.facts,
            source_reference="manual-profile-edit",
            source_type=FactSourceType.MANUAL_EDIT,
        )

    @app.post("/api/sessions/{session_id}/profile/confirm", response_model=Session)
    def confirm_profile(session_id: str) -> Session:
        return active.workflow.confirm_profile(session_id)

    @app.post("/api/sessions/{session_id}/resume-entries/propose", response_model=Session)
    def propose_resume_entries(session_id: str) -> Session:
        return active.resume_entries.propose(session_id)

    @app.put("/api/sessions/{session_id}/resume-entries/{entry_id}", response_model=Session)
    def update_resume_entry(session_id: str, entry_id: str, request: ResumeEntryEdit) -> Session:
        return active.resume_entries.edit(session_id, entry_id, request)

    @app.post(
        "/api/sessions/{session_id}/resume-entries/{entry_id}/approve", response_model=Session
    )
    def approve_resume_entry(session_id: str, entry_id: str) -> Session:
        return active.resume_entries.approve(session_id, entry_id)

    @app.delete("/api/sessions/{session_id}/resume-entries/{entry_id}", response_model=Session)
    def delete_resume_entry(session_id: str, entry_id: str) -> Session:
        return active.resume_entries.delete(session_id, entry_id)

    @app.post("/api/sessions/{session_id}/jobs/retrieve", response_model=Session)
    def retrieve_jobs(session_id: str) -> Session:
        return active.retrieve_jobs(session_id)

    @app.post("/api/sessions/{session_id}/jobs/{document_id}/select", response_model=Session)
    def select_job(session_id: str, document_id: str) -> Session:
        return active.workflow.select_job(session_id, document_id)

    @app.post(
        "/api/sessions/{session_id}/cvs",
        response_model=CVGenerationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def generate_cv(session_id: str) -> CVGenerationResponse:
        cv = active.generate_cv(session_id)
        return CVGenerationResponse(
            cv=cv,
            session=active.workflow.get_session(session_id),
        )

    @app.put("/api/sessions/{session_id}/cvs/{cv_id}", response_model=Session)
    def update_cv(session_id: str, cv_id: str, cv: CVDocument) -> Session:
        return active.cv.update(session_id, cv_id, cv)

    @app.post("/api/sessions/{session_id}/cvs/{cv_id}/validate", response_model=Session)
    def validate_cv(session_id: str, cv_id: str) -> Session:
        return active.cv.validate(session_id, cv_id)

    @app.post("/api/sessions/{session_id}/cvs/{cv_id}/export", response_model=Session)
    def record_export(session_id: str, cv_id: str) -> Session:
        return active.cv.record_export(session_id, cv_id)

    @app.get("/api/sessions/{session_id}/trace", response_model=TraceResponse)
    def get_trace(session_id: str) -> TraceResponse:
        return TraceResponse(events=active.workflow.get_session(session_id).trace)

    return app


app = create_app()
