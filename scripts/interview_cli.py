"""Text-mode practice interview that drives the interview flow without voice or UI.

Interview-flow component demo (Tien Dung). Typed answers stand in for final voice transcripts,
so the question plan, follow-up limits, skip/end and the time limit can be shown on their own.

    python scripts/interview_cli.py --profile 1 --job graduate_ai_engineer
    python scripts/interview_cli.py --profile 2 --pasted-job my_job.txt --title "Data Analyst"
    python scripts/interview_cli.py --planner openai      # model-planned questions (needs key)

During the interview type an answer, or:
    /skip               skip the current question
    /end                finish the interview now
    /followup <text>    answer, then propose a follow-up (as the voice model would)
"""

from __future__ import annotations

import argparse
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.domain.interview_models import (
    CreateInterviewRequest,
    FollowUpProposal,
    InterviewControlRequest,
    NextStepRequest,
    SkipQuestionRequest,
    StartInterviewRequest,
    TranscriptTurn,
    TurnEventRequest,
)
from app.domain.workflow import SessionWorkflow
from app.services.interview_flow import InterviewConflictError, InterviewFlowService
from interview_flow_tools import load_jobs, load_profiles, make_planner, prepare_session

CONNECTION_ID = "connection-cli"


def _wrap(text: str, prefix: str) -> str:
    return textwrap.fill(text, width=90, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def main() -> None:
    parser = argparse.ArgumentParser(description="Text-mode practice interview.")
    parser.add_argument("--profile", type=int, default=1, help="synthetic profile number (1-5)")
    parser.add_argument("--job", default="graduate_ai_engineer", help="supplied job document_id")
    parser.add_argument("--pasted-job", type=Path, help="text file containing a real JD")
    parser.add_argument("--title", default="Pasted job", help="title for --pasted-job")
    parser.add_argument("--type", choices=["behavioural", "technical", "mixed"], default="mixed")
    parser.add_argument("--minutes", type=int, choices=[5, 10, 15], default=10)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--follow-ups", type=int, default=1)
    parser.add_argument("--planner", choices=["template", "openai"], default="template")
    args = parser.parse_args()

    profile = load_profiles()[args.profile - 1]
    workflow = SessionWorkflow()
    service = InterviewFlowService(workflow, load_jobs(), make_planner(args.planner))
    session_id = prepare_session(workflow, profile)
    job = (
        {"source": "pasted_job", "title": args.title,
         "description": args.pasted_job.read_text(encoding="utf-8")}
        if args.pasted_job
        else {"source": "supplied_job", "document_id": args.job}
    )
    interview = service.create(
        session_id,
        CreateInterviewRequest.model_validate(
            {
                "request_id": f"cli-{uuid4()}",
                "job": job,
                "config": {
                    "interview_type": args.type,
                    "duration_minutes": args.minutes,
                    "main_question_count": args.count,
                    "max_follow_ups_per_question": args.follow_ups,
                },
                "consent": {"send_audio_to_provider": True, "retain_transcript_for_feedback": True},
            }
        ),
    )
    interview_id = interview.interview_id
    print(f"\nCandidate: {profile['name']} (synthetic)   Job: {interview.job.title}")
    print(f"{args.minutes} minutes, {args.count} main questions, planner: {args.planner}\n")
    print("Planned questions:")
    for index, question in enumerate(interview.questions, start=1):
        print(_wrap(question.text, f"  {index}. [{question.category}] "))
    input("\nPress Enter to start the interview...")

    started = service.start(
        session_id,
        interview_id,
        StartInterviewRequest(request_id="cli-start", expected_flow_revision=0,
                              connection_id=CONNECTION_ID),
    )
    step = started.next_step
    previous_turn: str | None = None
    started_at = started.interview.started_at
    while step.action == "ask_question":
        question = step.question
        remaining = args.minutes * 60 - (datetime.now(UTC) - started_at).total_seconds()  # type: ignore[operator]
        label = "Follow-up" if question.kind == "follow_up" else "Question"
        print(f"\n[{int(remaining // 60)}:{int(remaining % 60):02d} left] {label}:")
        print(_wrap(question.text, "  Interviewer: "))
        previous_turn = _record(service, session_id, interview_id, question.question_id,
                                "interviewer", question.text, previous_turn)
        raw = input("  You: ").strip()
        if raw == "/end":
            break
        if raw == "/skip" or not raw:
            step = service.skip(
                session_id, interview_id,
                SkipQuestionRequest(request_id=f"cli-{uuid4()}",
                                    expected_flow_revision=step.flow_revision,
                                    question_id=question.question_id),
            )
            continue
        proposal = None
        if raw.startswith("/followup "):
            follow_up_text = raw.removeprefix("/followup ").strip()
            raw = input("  Your answer first: ").strip() or "(no answer)"
            proposal = FollowUpProposal(text=follow_up_text, rationale="Proposed in the CLI demo.")
        answer_id = _record(service, session_id, interview_id, question.question_id,
                            "candidate", raw, previous_turn)
        previous_turn = answer_id
        try:
            step = service.next_step(
                session_id, interview_id,
                NextStepRequest(request_id=f"cli-{uuid4()}",
                                expected_flow_revision=step.flow_revision,
                                answered_question_id=question.question_id,
                                answer_turn_ids=[answer_id], follow_up_proposal=proposal),
            )
        except InterviewConflictError as error:
            print(f"  ! {error.code}: {error.message}")
            break
        if proposal is not None and (
            step.action != "ask_question" or step.question.kind != "follow_up"
        ):
            print("  (follow-up not accepted: limit reached, repeated, or not allowed)")

    current = service.get(session_id, interview_id)
    if current.phase == "active":
        current = service.end(
            session_id, interview_id,
            InterviewControlRequest(request_id="cli-end",
                                    expected_flow_revision=current.flow_revision),
        )
    print(f"\nInterview {current.phase} ({current.end_reason}).")
    for question in current.questions:
        print(_wrap(question.text, f"  - {question.status:<8} {question.kind:<9} "))


def _record(
    service: InterviewFlowService,
    session_id: str,
    interview_id: str,
    question_id: str,
    speaker: str,
    text: str,
    previous_turn: str | None,
) -> str:
    turn_id = f"turn-{uuid4()}"
    service.record_turn(
        session_id,
        interview_id,
        TurnEventRequest(
            event_id=f"event-{uuid4()}",
            connection_id=CONNECTION_ID,
            previous_turn_id=previous_turn,
            turn=TranscriptTurn(
                turn_id=turn_id,
                question_id=question_id,
                speaker=speaker,  # type: ignore[arg-type]
                input_mode="live_voice",
                transcript_version=1,
                transcript_status="final",
                text=text,
                delivery_status="complete" if speaker == "interviewer" else "not_applicable",
                timing=None,
            ),
        ),
    )
    return turn_id


if __name__ == "__main__":
    main()
