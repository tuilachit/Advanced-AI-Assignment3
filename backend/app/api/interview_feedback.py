from collections.abc import Callable

from fastapi import APIRouter, status

from app.domain.api_errors import ApiErrorBody, ApiErrorDetail
from app.domain.feedback_models import FeedbackRequest, FeedbackResponse, FeedbackStartResponse
from app.services.interview_feedback import InterviewFeedbackService


def build_feedback_router(service: Callable[[], InterviewFeedbackService]) -> APIRouter:
    router = APIRouter(
        prefix="/api/sessions/{session_id}/interviews/{interview_id}/feedback",
        tags=["interview-feedback"],
    )

    @router.post("", response_model=FeedbackStartResponse, status_code=status.HTTP_202_ACCEPTED)
    def start_feedback(
        session_id: str, interview_id: str, request: FeedbackRequest
    ) -> FeedbackStartResponse:
        return service().start(session_id, interview_id, request)

    @router.get("", response_model=FeedbackResponse)
    def get_feedback(session_id: str, interview_id: str) -> FeedbackResponse:
        result = service().get_result(session_id, interview_id)
        error = None
        if result.error is not None:
            error = ApiErrorBody(
                error=ApiErrorDetail(
                    code=result.error.code,
                    message=result.error.message,
                    details={"retryable": result.error.retryable},
                )
            )
        return FeedbackResponse(
            feedback_status=result.feedback_status, report=result.report, error=error
        )

    return router
