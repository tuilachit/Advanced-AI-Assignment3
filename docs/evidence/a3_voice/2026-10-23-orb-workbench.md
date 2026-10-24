# Voice orb workbench — 23 October 2026

## Scope

Luke approved a centred blue-white voice orb, distinct live activity states, round mute/end
controls, transcript below, mobile layout and reduced-motion support in the workbench only.
The main React interview UI remains Mio's responsibility; the native voice model is unchanged
at `gpt-realtime-2`. No new model or paid provider call was used for this visual refinement.

`VoiceOrbView` consumes the existing controller events. Orb movement reflects detected activity
states, not an audio amplitude measurement, inferred emotion or confidence. It is decorative;
the separate live status text and accessible controls expose its state without relying on colour.

## Checks and review repairs

- Four orb unit tests first failed before implementation, then passed: connection gating, real
  activity/mute priority, preservation of terminal/failed state through cleanup, and non-fatal
  warning handling.
- Browser checks cover explicit consent/preparation, circular layout at 390px width without
  horizontal overflow, reduced-motion animation suppression, and real controller/view wiring
  through interviewer speech, candidate speech, mute and finish.
- The wiring browser test replaces only external WebRTC/hardware and API boundaries. It does
  not contact OpenAI and is not a live voice quality evaluation.
- Desktop (1440px) and phone (390px) full-page screenshots were generated and visually inspected.
  No final-product mobile audio compatibility claim follows from these layout checks.
- Independent read-only review found additional voice control issues. Regression tests reproduced
  them before fixes: finalizing closed the channel too early; fatal engine errors did not expose
  a usable reconnect; failed ASR prevented a spoken retry; Skip did not stop the previous audio;
  channel closure after handshake did not release the microphone; mute erased playback flags.
- The fixes retain the ASR drain until terminal phase, clean up failed connections and re-enable
  reconnect, preserve failed evidence while accepting valid retries, cancel/clear old speech and
  serialize replacement questions, monitor channel close/error, and retain actual activity on mute.

Earlier real model checks, failures and synthetic-audio results remain separate in the
22 October evidence files. Human microphone accuracy, perceived naturalness and device-level
interruption reliability still require human trials; the orb does not establish those outcomes.

## Final local gates

- Backend: 278 tests passed in 10.04 seconds; Ruff passed; mypy found no issues in 25 files.
- Frontend: 65 unit/integration tests across seven files passed; ESLint, TypeScript and generated
  API-contract checks passed; production build passed.
- Playwright: all 13 browser tests passed in 47.5 seconds (10 existing CV regressions and three
  workbench checks). These are offline tests with controlled external boundaries.
- The independent reviewer rechecked the identified fixes, including the real finalizing payload
  with `current_question_id: null`, and confirmed no remaining blockers from those findings.
- Main React UI files are unchanged; the orb CSS is linked only by `voice-dev.html`.
- `git diff --check` passed. Targeted source/evidence scanning found no permanent-key/private-key
  patterns; local environment files remain untracked/ignored.
