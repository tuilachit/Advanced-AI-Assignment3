# Automatic interviewer questions — 23 October 2026

## Observation and limits

Luke reported that the interviewer was not speaking first. The finished in-app session
contained candidate transcripts (including "Hello.") but no visible interviewer transcript.
Its last displayed event was disconnected after user finish. Browser console inspection
returned no warnings or errors. Those observations do not identify why that particular
session lost its question; raw provider events from it were not retained.

A separate real-provider smoke test with synthetic context and muted fake microphone input
did produce the initial question and inbound audio. It did not reproduce Luke's silent session.
No human microphone recording was captured by these checks.

## Reproduced playback-readiness bug and repair

Three new regression tests failed before implementation:

- The controller requested question speech while its output element was still paused.
- A rejected autoplay request did not prevent that question from being spent into an
  inaudible stream; Enable audio did not request the waiting question.
- A newly issued question was also requested while playback was unavailable.

The adapter now queues issued-question speech while output playback is unavailable.
Successful playback activation resumes only a queued question, without duplicate requests.
The controller invokes that resume after remote-track playback or Enable audio succeeds.
The workbench clears the old playback warning when the candidate tries Enable audio.
Backend-issued question IDs, tools, progression and the `gpt-realtime-2` model are unchanged.
A fourth failing test reproduced a late playback rejection surfacing an error after disconnect.
Playback completion and rejection now both check that their audio element and engine still
belong to the current connection before resuming speech or displaying an error.

## Real-provider two-question rerun

Installed Chrome connected with real WebRTC and fake microphone hardware. Input tracks were
disabled; there was no candidate greeting or answer and no autoplay-bypass launch flag.
The first question was spoken automatically. After its output buffer stopped, the test
clicked Skip. The next backend-issued question was also spoken automatically.

Observed final interviewer transcripts:

1. "Why are you interested in the Graduate AI Engineer role, and what do you think you would
   bring to it?"
2. "This role mentions \"knowledge of machine-learning fundamentals, statistics, data analysis,
   agentic AI, LLMs, RAG, and domain-specific fine-tuning\". Which parts of Team Course Planner
   are most relevant to that, and how would you build on them here?"

Question IDs were `question-a178cc05-2882-4d31-8efa-d35d1dee46e2` and
`question-aa75adac-c682-4a58-847e-113407a2cd8c`. Both responses reached completed status and
both output audio buffers reported stopped. WebRTC reported 161,942 inbound audio bytes and
1,116 packets; the workbench displayed no error. Finish was then clicked and the test browser
was closed.

This verifies automatic real-provider output for first and skipped-to questions in installed
Chrome, not subjective listening quality, a candidate-answer progression rerun, or confirmed
playback in Luke's in-app browser. His original silent-session cause remains unconfirmed.

## Regression verification

- Backend: 278 tests passed; Ruff passed; mypy passed for 25 source files.
- Frontend final single-worker run: 69 tests passed across seven files.
- ESLint, TypeScript, generated API contract check and production build passed.
- Playwright final full run: 14 tests passed, including ready-output and blocked-then-enabled
  output cases using the real controller, adapter and workbench views with fake transport.
- Focused read-only review returned no actionable findings; `git diff --check` passed.

Earlier runs were not all green: the original browser transport fixture failed because it
never supplied a remote track. A first correction incorrectly constructed an RTCTrackEvent
without the receiver/transceiver fields; the fixture now dispatches a generic track event
carrying a MediaStream. Separately, a concurrent full-unit run timed out in three existing
tests: the whitespace-only resume-entry save, audit entry display, and valid PDF rendering.
The unchanged assertions all passed in the final full run with `--maxWorkers=1`; timeouts
were not increased and no tests were skipped. Resource contention is a suspected explanation,
not a measured root cause for those timing failures.

These repairs are local working-tree changes, not a new push, merge or deployment.
