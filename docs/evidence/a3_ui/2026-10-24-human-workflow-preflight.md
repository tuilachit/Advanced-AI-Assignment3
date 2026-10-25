# Integrated human voice workflow: preflight — 24 October 2026

**Historical preflight status: prepared; human microphone interaction and real feedback were pending.**
This record must not be presented as a successful human end-to-end interview.

The subsequent human run encountered interrupted playback and an unissued-response
error. The session later completed by its time limit and a real feedback report was
generated. See the [failure investigation](2026-10-24-voice-interruption-investigation.md)
for the preserved evidence, partial results and proposed work for review with Luke.
The pending checks below describe the original handoff, not the latest test status.

## Code checkpoint and automated checks

Local commit: `56ca40a825ca79cacddb6fec95527b57634bcc51`
(`feat(ui): integrate real interview voice and feedback APIs`).
Branch: `feature/interview-ui-integration`. The 24 committed files cover UI
bindings, feedback presentation/lifecycle, tests, fixtures and documentation.
`51eb2bf`, `efbd501` and merge `4b006c4` remain ancestors. No push or new merge.

Before committing, the following passed again:

- 166 frontend tests across 13 files; 33 Chrome browser regressions.
- ESLint, TypeScript, production build and staged whitespace checks.
- Both generated contracts matched fresh generation into an ignored temporary
  directory, with Windows line endings normalized for comparison.
- 10 focused Feedback HTTP API tests. The preceding Phase 2B check also passed
  all 281 feedback API/service/metrics/runtime tests.
- Staged scope and credential-pattern checks: no environment files, keys,
  dependencies, build outputs, backend/core voice changes or generated edits.

These automated UI/browser tests use mocked hardware/API responses. They do not
prove real microphone, audible playback, ASR quality or live feedback quality.
The known full-backend retrieval checksum baseline was not changed or rerun.

## Actual preparation performed

The ordinary application is running at `http://127.0.0.1:5173/`; its normal
FastAPI backend is on port 8000. Health returned 200/`ok`. Served Vite modules
contain the real controller and feedback bindings; the running OpenAPI exposes
the merged realtime and GET/POST feedback routes. No preview/workbench endpoint
or mocked route was used for this preparation.

The local key was configured by the user and was never printed. Read-only model
access checks succeeded for `gpt-5.6-luna`, `gpt-realtime-2` and
`gpt-4o-transcribe`. These checks establish access, not successful audio use.
The backend runs outside the execution sandbox because its outbound provider
connections were blocked inside it.

A dedicated, visible Chrome window uses the existing main app. It has no fake
microphone flags, mocked requests, pre-granted audio permission or injected
session state. It remains open for the user's real microphone interaction.

Synthetic data sources:

- Maya Chen, `student_profile_01` in
  [student_profiles.jsonl](../../../data/student_profiles.jsonl).
- Graduate AI Engineer, `graduate_ai_engineer` in
  [jobs.jsonl](../../../data/jobs.jsonl). Its exact description was pasted using
  the existing Interview Setup form. The resulting interview correctly records
  `job.source = pasted_job`; it is not represented as a retrieved job.

The app's live provider extracted the profile and proposed five resume entries.
The facts and proposed wording were reviewed against the sample source, corrected
as described below, and confirmed/approved through the existing UI. The live
question-planning POST returned HTTP 201 and three questions. A CV was optional
and was not generated for this short voice test; this is not evidence of a new
live CV-generation/export run.

Prepared identity:

- Session: `87bbb5cd-8805-43bd-bef5-2ccfaf9882b3`
- Interview: `interview-1b882277-41b2-4d25-800f-184548214380`
- Configuration: mixed, 5 minutes, 3 main questions, up to 1 follow-up each.
- Handoff snapshot: `phase = ready`, `started_at = null`, zero turns.
- Chrome microphone permission at handoff: `prompt`.

## Preparation issues and recovery

1. The first sandboxed model-access checks failed with connection errors.
   Checks succeeded outside the sandbox; the normal backend was restarted there.
   No application implementation or provider setting was changed.
2. Chrome initially opened before the restarted API was ready and displayed the
   existing API-unreachable message. A health check followed by reloading the
   empty workspace recovered. No populated workspace was reloaded.
3. Profile extraction initially omitted the first of the two supplied projects.
   A correction through the profile conversation preserved both projects in one
   project fact. This is an observed live extraction limitation.
4. The provider initially used `target_roles` (plural). The existing confirmation
   check requires `target_role`, so confirmation returned 409 for a missing target
   role. Clarifying the preferred role alone retained the plural field; requesting
   the canonical singular field through the conversation resolved it. The chosen
   Graduate Software Developer preference is from Maya's supplied sample. Record
   this as a CV profile-extraction/validation issue for coordination, not a voice
   or feedback failure. No unrelated core fix was made.

## Human test handoff

Use the already-open Chrome window. **Do not refresh or reopen the app**: the
current frontend creates a fresh workspace on a new page load, and sessions are
temporary in backend memory. Keep the backend and this tab open through feedback.

1. Click **Start interview**, allow Chrome's microphone prompt, and listen to the
   first question. If shown, click **Enable audio**. Confirm you can actually hear
   the interviewer; inbound audio or a caption alone does not prove audibility.
2. Answer as the synthetic Maya using the source facts: the Python/Flask/SQLite
   Course Planner, input validation and pytest tests; the coursework tool-call
   agent; and fictional retail teamwork. Do not invent quantified results to
   improve scores. Speak naturally for about 20–40 seconds per answer.
3. Answer at least two questions, allowing the interviewer to advance after each.
   Check listening/speaking states, current-question progress and the candidate
   transcript. Note exact errors, transcription differences or audible problems.
4. Choose **End interview → Finish interview** if it has not finished naturally.
   Wait for **Interview complete** and inspect the final transcript.
5. Choose **View feedback → Generate feedback**. Wait for ready or record the exact
   error and recovery. Check evidence links against what you actually said.
6. Tell the assistant whether the voice was audible, your answers appeared
   correctly, completion succeeded and feedback appeared. Leave the tab open so
   the canonical records can be checked before the backend stops.

## Evidence still to collect

| Check | Current result | Evidence needed |
| --- | --- | --- |
| Real AI question planning | Passed during preparation | Saved prepared interview and HTTP 201 |
| Real voice connection and AI question playback | Pending | Controller/UI state plus human confirmation of audibility |
| Human microphone input and transcription | Pending | Human observations plus final candidate turns |
| Answer submission and question progression | Pending | Answered question statuses and saved turn associations |
| Completion and microphone release | Pending | Canonical completed phase/end time, final revision, browser microphone indicator |
| Real feedback generation | Pending | GET status ready and server-produced report after explicit POST |
| Correct feedback identity and evidence | Pending | Matching interview/context/revision; exact quotes from final candidate turns for each question |

The local helper saves only canonical application records under ignored
`tmp/phase3-live/`: prepared identity, latest interview snapshot, completed
interview (when available), feedback status and ready report (when available).
It does not record raw audio, headers, credentials, realtime tokens, SDP or HARs.
These records will be reviewed and selectively copied into final evidence only
after the human test. The preparation screenshot is evidence of readiness only.

At this historical preflight checkpoint, there was **no human voice success or
real feedback result to report**. The subsequent investigation linked above
records partial real feedback success and the unresolved voice failures; the
[controlled comparison](2026-10-24-controlled-voice-comparison.md) records the
later headphone/speaker results.
