# Voice and feedback integration — 24 October 2026

Sunny's standalone PR #3 at `3fbcbb2cdfbe57e6524a4cbd2a2bbcf5247b606c` passed 550 backend
tests, Ruff, mypy, frontend contract checking and TypeScript in an isolated source snapshot.
Read-only review found no standalone merge blocker.

Combining it with voice required resolving `main.py`, `settings.py` and regenerated OpenAPI
and frontend schema files. Both features and all voice configuration fields were retained.

## Reproduced startup integration failure

Feedback rebuilds application services during startup. Keeping the old realtime route bound
to the pre-startup flow caused a valid active interview's token request to return 404. A new
test created and started the interview through the actual API after lifespan startup, then
asserted a successful credential response from a fake provider. It failed with 404 before
the correction and passed afterwards.

The naive combination also failed Sunny's existing test that prohibits reading credentials
or constructing SDK resources while generating OpenAPI. The correction moves default voice
provider creation into startup and shares the application-owned SDK client. Both interview
and voice routes resolve the same live flow; the provider proxy resolves the current lifespan's
provider. The workbench explicitly injects its provider because injected test services do not
implicitly read credentials.

A second offline regression test exercises the default provider without a provider override.
It mints a fake credential through the actual route, checks configured cedar/0.95/near-field
settings at the SDK boundary, prohibits a second SDK client and verifies client cleanup.

## Scope and limits

No new live OpenAI calls or microphone recordings were made in this integration round.
The voice workbench remains voice-only; its injected offline services do not generate live
feedback. The normal API provides the feedback endpoints. Final Mio UI integration and a
human end-to-end practice session remain separate acceptance work.

GitHub Actions now runs offline backend/frontend checks with read-only repository permissions,
pinned actions, no secrets and a blank API-key environment. Local and hosted results are
separate: a passing local run is not itself a passing hosted check or proof of a merge.

Final combined local checks: 561 backend tests, Ruff, mypy (32 files), 69 frontend unit tests,
ESLint, contract comparison, TypeScript/production build and 14 Playwright tests passed.
Read-only integration review found no blocker and requested the additional default-provider
regression coverage described above. PR #2's hosted backend/frontend checks passed before its
exact head `26ed86d08553ccb137c142008ef7ad80a10254a2` was explicitly approved and confirmed
merged. PR #3's updated hosted result and landing are separate subsequent checks.
