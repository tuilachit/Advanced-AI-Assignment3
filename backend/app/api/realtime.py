"""Luke's voice endpoint; lifecycle and transcript storage stay in Tien's service."""

from __future__ import annotations

import time

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import Field

from app.domain.models import StrictModel
from app.providers.base import ProviderError
from app.providers.realtime import RealtimeProvider
from app.services.interview_flow import InterviewConflictError, InterviewFlowService


class RealtimeCredential(StrictModel):
    client_secret: str = Field(min_length=1, repr=False)
    expires_at: int
    connection_id: str
    model: str


def build_realtime_router(
    flow: InterviewFlowService,
    provider: RealtimeProvider,
) -> APIRouter:
    router = APIRouter(prefix="/api/sessions/{session_id}/interviews", tags=["voice"])

    @router.post("/{interview_id}/realtime-token", response_model=RealtimeCredential)
    def token(
        session_id: str,
        interview_id: str,
        response: Response,
    ) -> RealtimeCredential | JSONResponse:
        response.headers["Cache-Control"] = "no-store"
        interview = flow.get(session_id, interview_id)
        if interview.phase != "active":
            raise InterviewConflictError("invalid_interview_phase", "Start the interview first.")
        try:
            issued = provider.issue(flow.get_context(session_id, interview_id))
            if (
                not isinstance(issued.get("client_secret"), str)
                or not issued["client_secret"]
                or not isinstance(issued.get("expires_at"), int)
                or issued["expires_at"] <= time.time()
            ):
                raise ValueError("Malformed credential")
        except (ProviderError, ValueError):
            return JSONResponse(
                status_code=503,
                headers={"Cache-Control": "no-store"},
                content={
                    "error": {
                        "code": "provider_unavailable",
                        "message": "The voice connection could not be prepared. Please retry.",
                        "details": {"retryable": True},
                    }
                },
            )
        # A failed provider request must not obsolete an existing healthy connection.
        # bind_connection re-checks phase after the external request, including the deadline.
        connection_id = flow.bind_connection(session_id, interview_id)
        return RealtimeCredential(
            client_secret=issued["client_secret"],
            expires_at=issued["expires_at"],
            connection_id=connection_id,
            model=provider.model,
        )

    return router
