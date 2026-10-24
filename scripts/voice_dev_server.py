"""Loopback-only voice workbench: synthetic approved context + offline question planner.

Real microphone audio uses the configured OpenAI Realtime model. This entry point is never
used by the normal app and does not add a synthetic-data endpoint to the normal API.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from app.domain.interview_models import InterviewConsent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)

    import uvicorn

    from app.domain.interview_models import CreateInterviewRequest, Interview
    from app.main import build_default_services, create_app
    from app.services.interview_flow import InterviewConflictError, InterviewFlowService
    from app.services.question_planner import TemplateQuestionPlanner
    from interview_flow_tools import load_profiles, prepare_session

    services = build_default_services()
    services.interviews = InterviewFlowService(
        services.workflow, services.jobs, TemplateQuestionPlanner()
    )
    app = create_app(services)

    @app.post("/api/voice-demo", response_model=Interview, status_code=201)
    def demo(consent: InterviewConsent) -> Interview:
        if not (consent.send_audio_to_provider and consent.retain_transcript_for_feedback):
            raise InterviewConflictError("consent_required", "Agree to audio and transcript use first.")
        session_id = prepare_session(services.workflow, load_profiles()[0])
        return services.interviews.create(session_id, CreateInterviewRequest.model_validate({
            "request_id": str(uuid4()),
            "job": {"source": "supplied_job", "document_id": "graduate_ai_engineer"},
            "config": {"main_question_count": 3},
            "consent": consent.model_dump(),
        }))

    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
