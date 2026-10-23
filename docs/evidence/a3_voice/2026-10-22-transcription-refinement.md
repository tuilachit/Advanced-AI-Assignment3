# Transcription and voice refinement — 22 October 2026

## Scope and observed regressions

Luke reported inaccurate words and messy transcript display during a real microphone trial.
No recording/reference transcript of that trial was supplied. Its word error rate and exact
acoustic cause therefore remain unknown; no synthetic result below substitutes for that trial.

Regression tests reproduced these implementation defects before the fixes:

- Replaying a provider delta with the same event ID appended its words twice.
- A final candidate transcript could be replaced by a conflicting late completion, after a late
  failure had also downgraded its state.
- The workbench rebuilt every conversation row on every delta rather than retaining stable rows.

The repaired adapter deduplicates event IDs, retains the first final text, ignores late transcript
failures/partials for finalized items and preserves speech registration order. The workbench
renderer has stable rows, hidden empty turns, explicit provisional labels and stale-version guards.
No answer-polishing model or fabricated transcript correction was introduced.

The native model remains `gpt-realtime-2`. Input ASR is separate. Its provisional default changes
from `gpt-4o-mini-transcribe` to `gpt-4o-transcribe`, with language `en` and a fixed vocabulary
hint. Laptop noise reduction is explicitly `far_field`; close headsets can use `near_field`.
Warm conversational delivery instructions are sent for each authorized question. Voice remains
`marin`, speed 1.0 and semantic VAD eagerness `low`; interruptions remain enabled.

## Controlled file-ASR comparison

Actual API calls used the same local macOS-synthesized audio file in four configurations.
This is synthetic English speech, not Luke's voice, and uses file transcription rather than
live WebRTC. Audio SHA-256:
`e5e28f63b24293464bf1931a796e5785abe137179b18e03518cf076c90c52ca6`.

The independently supplied reference was:

> I am interested in the graduate AI engineer role because I study computing science and have worked with Python and SQL. In our team course planner project, I built Python service logic and added tests for input validation. I would like to apply those skills and learn more about reliable AI systems.

WER used Levenshtein edits on lowercase word tokens, ignoring punctuation. The reference contains
52 tokens. Each returned transcript matched the reference under this normalization; capitalization
of Graduate AI Engineer differed between responses.

| Model | Explicit English and glossary | Word errors / reference words | WER |
| --- | --- | --- | --- |
| `gpt-4o-mini-transcribe` | No | 0 / 52 | 0.0 |
| `gpt-4o-mini-transcribe` | Yes | 0 / 52 | 0.0 |
| `gpt-4o-transcribe` | No | 0 / 52 | 0.0 |
| `gpt-4o-transcribe` | Yes | 0 / 52 | 0.0 |

Conclusion: a tie on this easy sample, not evidence that the full model is more accurate in this
application. The new default must still be evaluated with representative human speech, technical
names, actual microphones and background noise. It can be reverted through configuration if
quality/cost/latency does not justify it. No latency or cost advantage was measured here.

## Live browser rerun

Installed Chrome connected to the real provider using the same synthetic microphone fixture
(15 seconds of silence, the answer, then silence). Observed session configuration confirmed:

- Conversation: `gpt-realtime-2`.
- Transcription: `gpt-4o-transcribe`, `en`, the fixed glossary prompt.
- Noise reduction: `far_field`.
- Voice: `marin`, speed 1.0.
- Semantic VAD: `low`, automatic responses and interruptions enabled.

The actual final candidate transcript was:

> I am interested in the graduate AI Engineer role because I study computing science and have worked with Python and SQL in our team course planner project. I built Python service logic and added tests for input validation. I would like to apply those skills and learn more about reliable AI systems.

The actual next issued/spoken follow-up was:

> Can you share a specific example of how you validated correctness or handled edge cases in your Team Course Planner work?

The first transcript row remained the exact same DOM element after subsequent turns were
rendered (`stable_first_row: true`). No displayed provider error or page error occurred. Mute
displayed `Microphone muted`. Finish returned `completed · user_finished`.

This establishes real protocol compatibility, one synthetic answer/follow-up cycle, incremental
rendering and finish. No human listening quality result is claimed from a headless browser or
final text transcript. It does not establish microphone accuracy for Luke, a particular accent,
or naturalness on real speakers/headphones.

## Verification after the refinements

- Backend: 278 tests passed; Ruff passed; mypy found no issues in 25 source files.
- Frontend: 51 tests across six files passed; ESLint and TypeScript passed.
- Generated API contract check passed without changing Tien's interview wire types.
- Production build passed (normal application and separate voice workbench).
- The 10 existing CV browser regression tests passed. These are not ten live voice scenarios.
- New regressions include repeated deltas, late finalized-transcript replacement, reverse final
  arrival order, stable caption rows, stale display revisions, empty turns and plain-text safety.

The local development backend was restarted to load these settings, clearing its temporary
sessions. No GitHub push, merge, teammate message or deployment was performed.
