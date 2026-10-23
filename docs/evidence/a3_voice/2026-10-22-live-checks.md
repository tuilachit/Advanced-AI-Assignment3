# Voice integration checks — 22 October 2026

These are actual local checks, distinct from unit-test fixtures. API credentials are excluded.
Synthetic audio described here was generated locally with macOS speech synthesis, not recorded
from Luke or another student. Do not report it as a human usability evaluation.

## Model and credential checks

- The saved project key could retrieve model records for `gpt-realtime-2`,
  `gpt-4o-mini-transcribe` and `gpt-5.6-luna`.
- The real Realtime client-secret API accepted the configured native-audio session, semantic
  turn detection, input transcription, voice tools and required tool choice. A short-lived
  credential was created. Its value was not printed or saved.

## Native browser question smoke test

Headless installed Chrome connected using real WebRTC and the normal token endpoint.
The browser used fake microphone hardware and muted it after connection for this check.

The issued question and final interviewer transcript both concerned:

> Why are you interested in the Graduate AI Engineer role, and what do you think you would bring to it?

There were no page errors or displayed provider errors. This first check established browser
connection and the final response transcript; it did not by itself establish a candidate-answer
cycle, human listening quality or adaptation quality.

## Synthetic answer attempt — observed failure

The fixture contains 15 seconds of silence, a synthesized answer, then silence. The answer says:

> I am interested in the graduate AI engineer role because I study computing science and have worked with Python and SQL. In our team course planner project, I built Python service logic and added tests for input validation. I would like to apply those skills and learn more about reliable AI systems.

The actual input transcription preserved that answer. However the interview did not advance;
the displayed error was “The voice model returned an invalid action. No question was advanced.”
The browser test timed out while waiting for a follow-up. This attempt is a failure even though
microphone-fixture input and transcription worked. It must not be counted as end-to-end success.

Inspection of the actual completed provider tool response found a schema-shape mismatch:
`follow_up_proposal` was returned as a string question rather than the nested object expected
by the adapter. Both the arguments-done event and completed response contained the same value.
The observed cause was not a missing tool name.

The native tool now requests two flat string fields, `follow_up_question` and
`follow_up_rationale`. The adapter validates them, then maps them into Tien's unchanged nested
proposal contract. It dispatches only tools in completed `response.done` output, not intermediate
argument events that may also occur for cancelled responses. Regression tests cover valid flat
arguments, malformed arguments, incomplete/cancelled responses and duplicate events.

## Synthetic answer rerun — observed success

The repaired path was rerun against the real `gpt-realtime-2` provider in installed Chrome,
using the same synthesized answer fixture. Observations:

- WebRTC inbound audio: 177,851 bytes and 2,075 packets received.
- The first main question became `answered` after the final candidate transcript was saved.
- The application issued this follow-up, which also appeared as a final interviewer transcript:

  > Can you describe a time you handled incomplete or messy data, and what steps you took to validate and improve the outputs?

- Candidate transcription preserved the supplied answer, with minor capitalization differences.
- No page errors or displayed provider errors occurred.
- Clicking Finish returned interview phase `completed`, reason `user_finished`.

The first question's playback delivery was recorded as `complete`. The follow-up delivery was
still `unknown` at the snapshot; receiving its final transcript does not establish completed
playback. This proves one synthetic answer/follow-up round-trip and manual finish, not a full
multi-question human interview, interruption quality, or device compatibility.

## Live question-plan evaluation of Tien's component

The existing evaluation script ran against `gpt-5.6-luna` with all five supplied synthetic
profiles, two supplied jobs (`graduate_ai_engineer`, `rag_agent_engineer`), mixed interviews and
three main questions per plan. The actual generated artifacts are:

- `../a3_interview_flow/question_plans_openai_20261022-105131.json`
- `../a3_interview_flow/question_plans_openai_20261022-105131.md`

Automatic results: 10/10 valid plans, 30 questions, 27 citing approved evidence, 30 retaining
verbatim job excerpts, zero sensitive-wording flags, and zero identical plan pairs across five
same-profile/two-job comparisons. These automated checks do not constitute human grading or
prove every question is suitable. The Markdown lists every actual question for review.

## Final local regression checks

Run after the native-tool repair in this isolated voice checkout:

- Backend: `pytest backend/tests -o addopts='' -q` — 277 passed in 7.12 seconds.
- Ruff: `ruff check backend scripts/voice_dev_server.py` — passed.
- mypy: `mypy --config-file backend/pyproject.toml backend/app` — no issues in 25 files.
- Frontend: ESLint, TypeScript, generated API contract check — passed.
- Vitest: 44 tests across five files — passed (including 15 voice-specific tests).
- Production build: both main app and development voice entry point — passed.
- Playwright: 10 existing CV workflow browser tests — passed in 59.2 seconds.
  These are regression coverage for the existing app, not ten native-voice browser scenarios.
- `git diff --check` — passed. A targeted source/docs scan found no permanent OpenAI-key or
  private-key patterns. No local environment files are tracked in the voice checkout.

Changes remain local on `codex/voice-integration`, based on the reviewed PR head. No GitHub
merge, push, collaborator invitation or deployment was performed by this implementation.
