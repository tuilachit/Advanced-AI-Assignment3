# Manual live walkthrough — 25 October 2026

This is an observed run, not invented evaluation evidence. The candidate was the
clearly labelled Jamie Tran synthetic profile in `docs/demo/rich-synthetic-live-profile.md`.
The separate test app used frontend port 5174 and backend port 8001, preserving the
user's existing session on port 8000 during diagnosis. The test backend used the normal
application lifespan and shared 30-second OpenAI client, with only a test-origin CORS
addition. Model-operation timeout overrides were implemented in the provider itself.
Generation used `gpt-5.6-luna`; voice retained `gpt-realtime-2`.

## Root cause and repairs

- The user's resume-entry request logged `APITimeoutError`. The normal server had a
  30-second shared-client timeout, unlike earlier isolated checks with longer timeouts.
- A retry against the user's unchanged 19 confirmed facts, using the shared 30-second
  client plus the repaired provider override, produced 17 proposed entries in **39.98 s**.
  This was a separate provider regression check, not a manual browser run of that profile.
  No private profile text or contact details are included here.
- Profile interaction, entry generation/review and CV generation/validation now have a
  120-second per-request timeout. Realtime latency settings are unchanged. Timeouts are
  not automatically retried; explicit token-limit truncation has one bounded retry.
- Timeout failures have their own safe `provider_timeout` error rather than claiming
  a generic connection failure. Tests verify errors do not disclose provider payloads.
- The browser run exposed `contact_email` being omitted by exact-key consumers. Bounded
  contact aliases now feed CV generation and PDF rendering without broad prefix matching.
- PDF inspection exposed a duplicate name-only Summary and a bullet separated from its
  text at a page break. Name-only contact claims are excluded from Summary; bullet rows
  stay together. Two pages of the repaired export were rendered and inspected.
- The first offline browser run incorrectly reused the live frontend, whose 127.0.0.1 API
  override bypassed localhost-only mocks. It was stopped after failures. Browser checks
  now launch an exclusive port-5175 frontend with an explicit offline API root. The
  subsequent full run passed 36/36 checks. This is offline evidence, not live voice proof.

## Manual browser observations

Test session: `519bcadf-e5f0-413c-92a4-fdab189fc9e3`.

| Stage | Observed result |
| --- | --- |
| Enter rich profile | 12 draft facts extracted; readable assistant lists rendered |
| Confirm profile | Explicit confirmation succeeded |
| Generate entries | Six structured entries returned, initially unapproved |
| Review/approve | Education, skills, internship and three projects approved separately |
| Retrieve jobs | Exactly three results: `graduate_ai_engineer`, `agentic_ai_data_scientist`, `rag_agent_engineer` |
| Select job | Selected `graduate_ai_engineer` |
| Generate CV | Structured draft returned using approved entries |
| Validate | Evidence gate passed |
| Export | Downloaded actual A4 PDF; server recorded export; text extraction succeeded |
| Edit gating | Unsaved headline edit removed Download PDF; restoring exact validated text restored it |
| Evidence view | Facts, entry reviews, claim links, ranking audit and decision trace displayed |
| Interview setup | Mixed, five minutes, three main questions, one follow-up; validated CV included |
| Prepare/open room | Real question plan returned; room opened without automatically enabling microphone |

## Live voice acceptance

The user explicitly approved microphone activation and supplied spoken test answers.
The first two attempts connected and spoke the issued first question, but failed with
`unissued_question` during candidate transcription. The microphone was released on error.
This was not recorded as a pass. Inspection found that the guard treated every assistant
message as audio, including text-only control responses. A narrow modality-aware repair
allows explicitly text-only messages without storing them as interviewer speech, while
retaining rejection of unknown/unissued audio and metadata mismatches. Regression tests
cover both the false positive and attempts to emit audio from a text-labelled response.

The final retry connected successfully, replayed the issued question, saved the user's
spoken answer, advanced to an authorised follow-up, and spoke that follow-up with the
microphone paused until playback finished. Safe development diagnostics showed text-only
control/function-call responses and metadata-bearing audio responses as distinct events.
It did not reproduce the earlier error on this retry; this is one acceptance run, not a
guarantee of future provider reliability or proof of transcription accuracy for all accents.

At the time limit, the interview completed and the microphone was released. Actual result:
one main question answered, one follow-up answered, two planned main questions not asked.
The record contained 12 turns, including unavailable transcription from earlier failed
connections. Feedback generation succeeded through the UI and quoted saved candidate
answers. The unasked questions were unassessed, missing pause analysis was marked
unavailable, and transcription gaps were explicitly disclosed. No scores are presented as
ground truth. A misleading completed-room label claiming no question had been issued was
also repaired and covered by a regression test.

Interview ID: `interview-94eecd68-5863-4bd2-b624-c4ac1735ef2a`.
The normal port-8000 backend was restarted after verification using the existing local key;
its temporary sessions were cleared as previously authorised. The separate test session
remains on port 8001, with its feedback page open on port 5174.

## Verification scope

No fake transcripts, scores or feedback were inserted into the live run. Unit/browser
simulations remain separate evidence. No key or private Luke profile is committed here.
Changes remain local and uncommitted; no deployment or PR merge is claimed.

Verification commands use the documented project configurations. An exploratory mypy
invocation without the Pydantic plugin reported settings-type errors; the documented
`mypy --config-file backend/pyproject.toml backend/app` passes. Explicitly forcing Ruff's
config from the root also changed import classification; the documented `ruff check backend`
passes without rewriting unrelated test imports.

Final local verification after the repairs: 632 backend tests and 199 frontend unit
tests passed. Backend Ruff and mypy (33 source files), frontend ESLint, TypeScript and
production build passed. The isolated browser suite passed all 36 checks; its final
run record reports `passed` with no failed tests. API contract checking passed and
`git diff --check` was clean. Both normal application endpoints (5173 frontend and
8000 OpenAPI) returned HTTP 200 after restart. These checks do not substitute for
the bounded live acceptance described above.

During pre-PR verification, the preview cancellation browser test exposed a timing
race in its setup: under load the 650 ms simulated handshake finished before the
test clicked Disconnect, so the UI correctly offered Reconnect rather than Start.
The test now controls the browser clock, cancels while the handshake is pending,
then advances beyond its deadline to verify that the cancelled connection cannot
activate. The application handshake duration and cancellation behavior are unchanged.
Temporary development-only voice event-shape diagnostics were removed before commit.
