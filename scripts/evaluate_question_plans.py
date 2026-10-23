"""Evaluate interview question plans across the synthetic profiles and several jobs.

Interview-flow component check (Tien Dung). For every profile x job it creates a real interview
through ``InterviewFlowService`` (so the same validation and retry are used) and records:

- whether a valid plan was produced, and the question categories;
- grounding: questions citing approved evidence, and JD excerpts (always verbatim if present);
- job specificity: how much two jobs' plans overlap for the same candidate;
- sensitive wording found in planned questions (should be zero).

Usage (from the project root, with the virtual environment active):

    python scripts/evaluate_question_plans.py --planner template
    python scripts/evaluate_question_plans.py --planner openai      # needs OPENAI_API_KEY

Writes ``docs/evidence/a3_interview_flow/question_plans_<planner>_<timestamp>.{json,md}``.
Automatic checks do not replace reading the questions: the Markdown file lists them all.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.interview_models import CreateInterviewRequest
from app.domain.workflow import SessionWorkflow
from app.providers.base import ProviderError
from app.services.interview_flow import InterviewFlowService, follow_up_problem
from interview_flow_tools import (
    PROJECT_ROOT,
    load_jobs,
    load_profiles,
    make_planner,
    prepare_session,
)

DEFAULT_JOBS = ["graduate_ai_engineer", "computer_vision_engineer", "healthcare_ml_engineer"]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "evidence" / "a3_interview_flow"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) >= 3}


def _jaccard(first: set[str], second: set[str]) -> float:
    return len(first & second) / len(first | second) if first | second else 1.0


def evaluate(
    planner_kind: str, job_ids: list[str], interview_type: str, count: int
) -> dict[str, Any]:
    jobs = {job.document_id: job for job in load_jobs()}
    missing = [job_id for job_id in job_ids if job_id not in jobs]
    if missing:
        raise SystemExit(f"Unknown job IDs: {missing}")
    workflow = SessionWorkflow()
    service = InterviewFlowService(
        workflow, list(jobs.values()), make_planner(planner_kind), scheduler=lambda *_: None
    )
    runs: list[dict[str, Any]] = []
    for profile in load_profiles():
        session_id = prepare_session(workflow, profile)
        for job_id in job_ids:
            request = CreateInterviewRequest.model_validate(
                {
                    "request_id": f"eval-{uuid4()}",
                    "job": {"source": "supplied_job", "document_id": job_id},
                    "config": {"interview_type": interview_type, "main_question_count": count},
                    "consent": {
                        "send_audio_to_provider": True,
                        "retain_transcript_for_feedback": True,
                    },
                }
            )
            run: dict[str, Any] = {"profile": profile["document_id"], "job": job_id}
            try:
                interview = service.create(session_id, request)
            except ProviderError as error:
                run.update(valid=False, error=str(error), questions=[])
                runs.append(run)
                continue
            questions = [q.model_dump(mode="json") for q in interview.questions]
            run.update(
                valid=True,
                questions=questions,
                personalised=sum(bool(q["fact_ids"] or q["resume_entry_ids"]) for q in questions),
                with_excerpt=sum(q["job_requirement_excerpt"] is not None for q in questions),
                categories={
                    c: sum(q["category"] == c for q in questions)
                    for c in ("behavioural", "technical")
                },
                sensitive=[
                    q["text"]
                    for q in questions
                    if follow_up_problem(q["text"]) == "sensitive_topic"
                ],
            )
            runs.append(run)

    overlaps: list[dict[str, Any]] = []
    for profile in load_profiles():
        plans = {
            r["job"]: r["questions"]
            for r in runs
            if r["profile"] == profile["document_id"] and r["valid"]
        }
        for first, second in combinations(job_ids, 2):
            if first not in plans or second not in plans:
                continue
            texts_a = {q["text"] for q in plans[first]}
            texts_b = {q["text"] for q in plans[second]}
            overlaps.append(
                {
                    "profile": profile["document_id"],
                    "jobs": [first, second],
                    "identical_questions": len(texts_a & texts_b),
                    "token_jaccard": round(
                        _jaccard(
                            _tokens(" ".join(sorted(texts_a))), _tokens(" ".join(sorted(texts_b)))
                        ),
                        3,
                    ),
                }
            )

    valid_runs = [r for r in runs if r["valid"]]
    total_questions = sum(len(r["questions"]) for r in valid_runs)
    summary = {
        "plans": len(runs),
        "valid_plans": len(valid_runs),
        "questions": total_questions,
        "personalised_questions": sum(r["personalised"] for r in valid_runs),
        "questions_with_jd_excerpt": sum(r["with_excerpt"] for r in valid_runs),
        "sensitive_questions": sum(len(r["sensitive"]) for r in valid_runs),
        "job_pairs": len(overlaps),
        "job_pairs_with_identical_plans": sum(
            o["identical_questions"] == count for o in overlaps
        ),
        "mean_identical_questions_per_job_pair": round(
            sum(o["identical_questions"] for o in overlaps) / len(overlaps), 2
        )
        if overlaps
        else None,
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "planner": planner_kind,
        "config": {"interview_type": interview_type, "main_question_count": count},
        "jobs": job_ids,
        "summary": summary,
        "job_pair_overlap": overlaps,
        "runs": runs,
    }


def to_markdown(result: dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        f"# Question plan evaluation ({result['planner']} planner)",
        "",
        f"Generated {result['generated_at']}. Config: {result['config']}. "
        f"Jobs: {', '.join(result['jobs'])}. Profiles: the five synthetic profiles.",
        "",
        "Automatic checks only. Read the questions below before using them as evidence.",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Valid plans | {s['valid_plans']} / {s['plans']} |",
        f"| Questions | {s['questions']} |",
        f"| Questions citing approved evidence | {s['personalised_questions']} |",
        f"| Questions with a verbatim JD excerpt | {s['questions_with_jd_excerpt']} |",
        f"| Questions with sensitive wording | {s['sensitive_questions']} |",
        f"| Job pairs with identical plans (same candidate) | "
        f"{s['job_pairs_with_identical_plans']} / {s['job_pairs']} |",
        f"| Mean identical questions per job pair | {s['mean_identical_questions_per_job_pair']} |",
        "",
    ]
    for run in result["runs"]:
        lines.append(f"## {run['profile']} — {run['job']}")
        lines.append("")
        if not run["valid"]:
            lines += [f"No valid plan: {run['error']}", ""]
            continue
        for index, question in enumerate(run["questions"], start=1):
            refs = "evidence" if question["fact_ids"] or question["resume_entry_ids"] else "generic"
            excerpt = question["job_requirement_excerpt"]
            lines.append(
                f"{index}. *{question['category']}, {refs}* — {question['text']}"
                + (f"  \n   JD excerpt: “{excerpt}”" if excerpt else "")
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--planner", choices=["template", "openai"], default="template")
    parser.add_argument("--jobs", nargs="+", default=DEFAULT_JOBS)
    parser.add_argument("--type", choices=["behavioural", "technical", "mixed"], default="mixed")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    result = evaluate(args.planner, args.jobs, args.type, args.count)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = args.output_dir / f"question_plans_{args.planner}_{stamp}"
    base.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(result) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"Wrote {base.with_suffix('.md')}")


if __name__ == "__main__":
    main()
