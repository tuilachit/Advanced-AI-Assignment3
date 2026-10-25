# Proposed title

feat(ui): integrate interview setup, real voice and feedback

# Proposed Draft PR body

## Summary

Adds a responsive interview workspace to Evidence CV, from CV Builder navigation and Interview Setup through the real voice controller to canonical-transcript feedback. This is Mio's UI & Integration contribution.

**Draft: the integrations are implemented, but real voice acceptance remains incomplete.** The controlled speaker test reproduced false VAD interruption, and the separate `unissued_question` investigation still needs coordination with Luke. No merge is requested.

## Completed functionality

- Interview navigation and **Practise interview** from a validated, export-ready CV; existing CV editing, validation and PDF export remain intact.
- Interview Setup uses Tien's merged flow API with job/context selection, optional validated CV, configuration, consent, loading/error states and stable retry IDs.
- Live Interview binds Luke's existing `RealtimeVoiceController(interviewApi(sessionId))` through `voiceBridge.ts` and React hooks. It displays connection/activity, questions, progress, countdown and transcript events, and connects start, mute, skip, reconnect, playback recovery and finish.
- Controller-owned audio/WebRTC cleanup, UI lifecycle handling, read-only snapshot polling and canonical final-transcript handoff are covered by integration tests.
- Feedback uses Sunny's existing GET/POST endpoints and generated types. Generation is explicit after completion; the UI handles generating/ready/failed states, serial polling and retries.
- Feedback validates interview ID, context hash and transcript revision before displaying question criteria, applicable STAR assessments, speaking metrics, exact transcript evidence and suggestions. Unavailable values stay unavailable; no overall score is invented.
- Responsive layouts and modular components retain the Evidence CV design. Scripted interview and synthetic feedback previews remain explicitly labelled and separate from real API data.

## Scope

Feature code is under `frontend/src/features/interview/`, with limited navigation, API client, type-alias and test additions. Relative to current `main`, this branch does not change the backend, Luke's voice core, generated schemas, dependencies or datasets. No teammate implementation is duplicated or patched.

The existing commits `51eb2bf`, `efbd501`, merge `4b006c4` and integration `56ca40a` are preserved. Environment files, credentials, raw diagnostic traces, recordings, logs, dependencies and temporary/build artifacts are excluded.

## Fresh automated validation — 24 October 2026

| Check | Result |
| --- | --- |
| Frontend unit/component/integration tests | **166 passed**, 13 files |
| Chrome browser regressions | **33 passed**, including existing CV workflow/export and interview/feedback flows |
| ESLint, TypeScript and Vite production build | Passed |
| Fresh OpenAPI and TypeScript contract generation | Matches committed files after Windows newline normalization; no generated edits |
| Backend Ruff / mypy | Passed; mypy checked 32 source files |
| Full backend suite with Python UTF-8 mode | **560 passed, 1 known baseline failure** |

The backend failure is `test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid`: the Windows CRLF checkout changes the raw `data/jobs.jsonl` checksum. LF-normalizing bytes in memory matches the frozen baseline; no file was changed. The initial default-locale run had **559 passed, 2 failed**, including a CP932 decoding error in an existing artifact test. Running unchanged source with `python -X utf8 -m pytest backend/tests` resolves that encoding failure and leaves only the documented checksum baseline.

These automated tests mock hardware/provider/API responses where applicable. They are not evidence of a successful real microphone interview.

## Real observations and known voice issues

- **Headphones:** the user heard the entire first question; approximately 9.16 seconds of output-buffer playback, no VAD trigger while silent.
- **Laptop speakers:** same microphone, effective voice settings and question; VAD started about 1.841 seconds into playback, then the provider cleared audio and cancelled with `turn_detected`. The user was silent. An unexpected input transcription arrived about 2.34 seconds after the cutoff. Speaker pickup is strongly supported; the exact acoustic source is unproven because raw audio was not recorded.
- The speaker comparison did **not** reproduce `unissued_question`; its automatic response only called `continue_listening`. Separately, an offline replay of the unchanged adapter shows an unrelated `response.created` can consume a pending question permit. The original live failure's exact event ordering remains unknown.
- The original interrupted run saved a substantive answer, advanced once, completed by time limit and produced real feedback matching its interview/context/transcript revision, with four exact evidence quotes. This is partial success, not full voice acceptance.
- Safety checks, voice policy and canonical diagnostic data remain intact. The UI's generic **Connection lost** label can follow a controller safety shutdown; it does not establish a network outage.

## Remaining coordination and acceptance

- Coordinate with Luke on speaker/VAD interruption policy, generated text versus audible delivery, and strict correlation of automatic responses versus explicitly issued questions. Preserve unissued-output rejection and resource cleanup.
- Add targeted regression coverage with any agreed voice-core repair, including completed-then-cancelled events during playback and automatic responses arriving while a speech permit is pending.
- Repeat a real human interview through audible questions, substantive answers, progression, completion and evidence-matched feedback. Keep this acceptance separate from previews and mocked tests.
- Sessions remain temporary in backend memory; refresh/history persistence is outside this checkpoint. Visual polish and advanced animation follow separately.

See [publication checks](docs/evidence/a3_ui/2026-10-24-pr-publication-checks.md), [real voice integration](docs/a3/real-voice-ui-integration.md), [real feedback integration](docs/a3/real-feedback-ui-integration.md), [original failure investigation](docs/evidence/a3_ui/2026-10-24-voice-interruption-investigation.md) and [controlled comparison](docs/evidence/a3_ui/2026-10-24-controlled-voice-comparison.md). The reports summarize observations; ignored raw diagnostic artifacts are retained locally and are not part of this PR.
