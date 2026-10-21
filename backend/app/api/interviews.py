"""Interview-flow routes (Interface Contract v1, section 9).

Owned here: create, get, start, next-step, skip, end, cancel and transcript turn storage.
The realtime-token route (voice) and feedback routes are added by their owners.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.interview_models import (
    AskQuestionStep,
    CreateInterviewRequest,
    FinishStep,
    Interview,
    InterviewControlRequest,
    NextStepRequest,
    SkipQuestionRequest,
    StartInterviewRequest,
    StartInterviewResponse,
    TurnEventAck,
    TurnEventRequest,
)
from app.services.interview_flow import InterviewError, InterviewFlowService

PREFIX = "/api/sessions/{session_id}/interviews"


def build_interview_router(service: InterviewFlowService) -> APIRouter:
    router = APIRouter(prefix=PREFIX, tags=["interviews"])

    @router.post("", response_model=Interview, status_code=status.HTTP_201_CREATED)
    def create_interview(session_id: str, request: CreateInterviewRequest) -> Interview:
        return service.create(session_id, request)

    @router.get("/{interview_id}", response_model=Interview)
    def get_interview(session_id: str, interview_id: str) -> Interview:
        return service.get(session_id, interview_id)

    @router.post("/{interview_id}/start", response_model=StartInterviewResponse)
    def start_interview(
        session_id: str, interview_id: str, request: StartInterviewRequest
    ) -> StartInterviewResponse:
        return service.start(session_id, interview_id, request)

    @router.post("/{interview_id}/next-step", response_model=AskQuestionStep | FinishStep)
    def next_step(
        session_id: str, interview_id: str, request: NextStepRequest
    ) -> AskQuestionStep | FinishStep:
        return service.next_step(session_id, interview_id, request)

    @router.post("/{interview_id}/skip", response_model=AskQuestionStep | FinishStep)
    def skip_question(
        session_id: str, interview_id: str, request: SkipQuestionRequest
    ) -> AskQuestionStep | FinishStep:
        return service.skip(session_id, interview_id, request)

    @router.post("/{interview_id}/end", response_model=Interview)
    def end_interview(
        session_id: str, interview_id: str, request: InterviewControlRequest
    ) -> Interview:
        return service.end(session_id, interview_id, request)

    @router.post("/{interview_id}/cancel", response_model=Interview)
    def cancel_interview(
        session_id: str, interview_id: str, request: InterviewControlRequest
    ) -> Interview:
        return service.cancel(session_id, interview_id, request)

    @router.post("/{interview_id}/turns", response_model=TurnEventAck)
    def record_turn(
        session_id: str, interview_id: str, request: TurnEventRequest
    ) -> TurnEventAck:
        return service.record_turn(session_id, interview_id, request)

    return router


def register_interview_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(InterviewError)
    async def interview_error(_request: Request, error: InterviewError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {"code": error.code, "message": error.message, "details": error.details}
            },
        )
