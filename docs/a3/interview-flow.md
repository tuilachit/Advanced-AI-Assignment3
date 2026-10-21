# A3 Interview Flow (Tien Dung)

Component: question planning, pasted job descriptions, question progression, time limits and the
interview lifecycle. It implements the interview-flow parts of *A3 Mock Interview — Shared
Interface Contract v1* (sections 3–6 and 9).

## Files

| File | Purpose |
| --- | --- |
| `backend/app/domain/interview_models.py` | Pydantic wire models (`Interview`, `InterviewQuestion`, `TranscriptTurn`, requests, `NextStep`) |
| `backend/app/services/interview_flow.py` | In-memory interview store, context snapshot, progression, limits, lifecycle, turn storage |
| `backend/app/services/question_planner.py` | Planner protocol, plan validation, offline template planner |
| `backend/app/providers/openai_interview_planner.py` | OpenAI structured-output question planner and its prompt |
| `backend/app/api/interviews.py` | FastAPI routes and the interview error handler |
| `backend/tests/test_interview_flow.py` | 51 offline tests for this component |
| `scripts/evaluate_question_plans.py` | Question-plan evaluation across the 5 synthetic profiles and several jobs |
| `scripts/interview_cli.py` | Text-mode practice interview that drives the flow without voice or UI |
| `scripts/interview_flow_tools.py` | Shared helpers for the two scripts (profile → confirmed facts and approved entries) |

`backend/app/main.py` only wires the service and router in. Existing CV Builder routes are unchanged.

## Routes (all under `/api/sessions/{session_id}/interviews`)

| Method / path | Result |
| --- | --- |
| `POST /` | Freeze context, plan questions, return 201 `Interview` in `ready` |
| `GET /{id}` | Current `Interview` (also applies the deadline and finalization drain) |
| `POST /{id}/start` | `ready → active`; returns `{interview, next_step}` with the first question |
| `POST /{id}/next-step` | Submit final answer turns; returns `ask_question` or `finish` |
| `POST /{id}/skip` | Record the current question as skipped; returns the next step |
| `POST /{id}/end` | `active → finalizing → completed` (`user_finished`) |
| `POST /{id}/cancel` | `ready/active → cancelled` |
| `POST /{id}/turns` | Store a normalized transcript event (called by the voice adapter) |

`realtime-token` (Luke) and `feedback` (Sunny) are added by their owners.

## How it works

1. **Create.** The backend reads the session itself: confirmed facts and approved resume entries
   are required; a CV is optional and must be the current validated CV. The job is either a
   supplied job (`document_id`) or a pasted job (title ≤ 200, description ≤ 20,000 characters).
   Pasted jobs are interview context only: they are not added to `data/jobs.jsonl` and are never
   candidate evidence. Everything is copied into a frozen snapshot; `context_hash` is SHA-256 of
   its canonical JSON. Later profile/CV edits do not change existing interviews.
2. **Plan.** The planner returns `main_question_count` (3–6) questions. `validate_plan` checks
   every question before the interview is created: count, duplicates, category versus
   `interview_type`, and that `fact_ids` / `resume_entry_ids` exist in the snapshot. A
   `job_requirement_excerpt` must be verbatim: a whitespace/case variant is mapped back to the
   exact text, and a paraphrase is dropped (`null`). If validation fails, the planner is asked
   once more with the list of problems; a second failure returns a recoverable 503 and no
   interview is stored.
3. **Progress.** This service is the only authority for question order. `next-step` accepts a
   follow-up proposal from the voice agent only while the main question is below
   `max_follow_ups_per_question` (0–2), the text is not a repeat, and it passes the follow-up
   policy (`follow_up_problem`): at most 300 characters, an actual question, and no personal
   or protected topic such as age, nationality, visa, religion, family, health or disability.
   A rejected proposal is not recorded; the next planned main question is issued instead, or
   the interview finishes with `questions_complete`. Answers must
   be final candidate turns registered for the current question and not used before;
   `transcript_pending` (retryable, same `request_id`) and `transcript_failed` are returned
   instead of inventing an answer.
4. **Time limit.** `start` sets a deadline (5/10/15 minutes) and schedules a deadline task, so
   the interview is finalized on time even if no request arrives (for example, the candidate
   stays silent). Every request also checks the deadline. No new question is issued when less
   than 30 seconds remain. On expiry captured answers for the current question are submitted
   and the interview ends with `time_limit`.
5. **Finalize.** `end` (or a deadline/finish) stops new questions and waits up to 10 seconds for
   registered pending transcripts. Transcripts that never finalize are marked `failed`, never
   filled in. The current question's final answer is submitted once, even without a
   `next-step` call.
6. **Safety of retries.** `start`, `next-step`, `skip`, `end` and `cancel` use `request_id`
   (same input → same response; changed input → 409) and `expected_flow_revision` (stale → 409).
   Turn events are deduplicated by `event_id`; a partial never overwrites a final; a submitted
   answer cannot be edited; turns from an obsolete connection cannot create new turns.

## Hooks for the other components

- **Voice (Luke):** `service.bind_connection(session_id, interview_id)` returns a new
  `connection_id` for the token route and makes older connections obsolete.
  `service.fail(...)` records an unrecoverable provider failure. Turn storage and its rules are
  implemented here, so the adapter only posts normalized events to `/turns`.
- **Feedback (Sunny):** `get_context(...)` returns the frozen snapshot, `submitted_turn_ids(...)`
  the candidate turns that were explicitly submitted, and `set_feedback_status(...)` updates
  `feedback_status`.
- **UI (Mio):** regenerate types with `npm --prefix frontend run contract:generate`; they are
  already regenerated on this branch.

## Decisions and limitations

- Consent: both consent values are stored with the interview and required by `start` (live audio
  cannot begin without them).
- Deadline and drain timers run in a background thread (`threading.Timer`) and are also enforced
  on every read/change, so a missed timer cannot leave an interview running past its limit.
- The question planner uses `OPENAI_INTERVIEW_MODEL` when it is set, otherwise the existing
  `OPENAI_MODEL`. Without an API key, creation returns 503. A test checks that the plan schema
  converts to OpenAI strict structured-output format offline.
  Tests and the local demo use `TemplateQuestionPlanner`, which only reuses approved-entry and
  job wording and is far less natural.
- Not yet run against the live OpenAI API (no key on the author's machine). Before merging,
  run one interview creation with a real key and check the questions, e.g.
  `python scripts/evaluate_question_plans.py --planner openai`.
- In-memory only: a backend restart loses interviews, as with existing sessions.

## Scripts

Run from the project root with the virtual environment active.

```bash
# Question-plan evaluation (offline baseline; add --planner openai with a key)
python scripts/evaluate_question_plans.py --planner template
# Text-mode practice interview (typed answers stand in for voice transcripts)
python scripts/interview_cli.py --profile 1 --job graduate_ai_engineer
```

The evaluation writes `docs/evidence/a3_interview_flow/question_plans_<planner>_<time>.{md,json}`.
The committed template-planner run (5 profiles × 3 jobs, mixed, 4 questions) is a baseline only:
15/15 valid plans, 60 questions, 36 citing approved evidence, 30 with a verbatim JD excerpt,
0 with sensitive wording, and no job pair with an identical plan for the same candidate. The
template planner links requirements to entries by shared keywords, so some links are weak; the
model planner must be evaluated separately with a live key.
