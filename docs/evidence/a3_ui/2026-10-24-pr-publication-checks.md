# UI integration publication checks — 24 October 2026

Branch: `feature/interview-ui-integration`. Tested application commit:
`56ca40a825ca79cacddb6fec95527b57634bcc51`. This publication preparation changes
documentation only; application code is unchanged from that tested commit.

## Scope and history

Fetched `origin` before review. Existing commits `51eb2bf`, `efbd501`, merge
`4b006c4` and integration `56ca40a` remain in the branch history. No rebase,
amend, reset, merge, force push or teammate branch change is part of publication.

The feature diff against `origin/main` contains UI components and adapters,
limited shared navigation/client/type additions, tests, preview pages and
documentation. Backend source, `frontend/src/voice/`, generated OpenAPI/types,
package manifests/lockfiles and datasets match `origin/main`.

The three previously untracked investigation reports were reviewed for inclusion.
Their historical status statements were clarified so the preflight's pending
checks cannot be mistaken for the later diagnostic results. The PR description
in `docs/a3/ui-draft-pr.md` now describes the implemented real integrations,
separate synthetic previews, test evidence and remaining voice acceptance gaps.

Only reviewed Markdown documentation is added in this publication commit.
`.env.local`, temporary recordings/traces, logs, local credentials, dependencies,
browser profiles and build/test outputs remain excluded. Local-only evidence
paths in the reports identify preserved artifacts, not files included in GitHub.

## Fresh checks

All test commands set `OPENAI_API_KEY` to an empty process-local value. They do
not change the running application's environment or the local credential file.

| Command/check | Result |
| --- | --- |
| `npm --prefix frontend test -- --run --maxWorkers=1` | 166 passed in 13 files |
| `npm --prefix frontend run e2e` | 33 passed in installed Chrome |
| `npm --prefix frontend run lint` | Passed |
| `npm --prefix frontend run build` | Passed; includes `tsc -b` and Vite build |
| Windows equivalent of `contract:check` | Fresh OpenAPI and generated TypeScript match after newline normalization |
| `.venv/Scripts/python.exe -m ruff check backend` | Passed |
| `.venv/Scripts/python.exe -m mypy --config-file backend/pyproject.toml backend/app` | Passed, 32 source files |
| `.venv/Scripts/python.exe -m pytest backend/tests` | 559 passed, 2 failed; failures detailed below |
| `.venv/Scripts/python.exe -X utf8 -m pytest backend/tests` | 560 passed, 1 existing checksum failure |

Contract generation used `backend/export_openapi.py` and the installed
`openapi-typescript --alphabetize`, writing only to ignored
`tmp/pr-publish-checks/`. Tracked generated files were not rewritten.

The initial backend run encountered the existing artifact test
`test_imported_profiles_keep_approved_entry_sources_in_their_own_session[supplied-five-5]`
reading UTF-8 output with this Windows machine's default CP932 encoding. An
unchanged-source full rerun with Python UTF-8 mode passed that test. No application
or test patch was made for this environment-specific issue.

The remaining failure is the previously documented
`test_retrieval_baseline.py::test_committed_embedding_baseline_is_valid`.
The raw checksum of the CRLF checkout of `data/jobs.jsonl` differs from the frozen
baseline. Replacing CRLF with LF in memory produces the expected checksum. The
dataset, checkout settings, verifier and baseline were not modified.

Browser coverage includes the existing CV review/approval workflow, validation
and PDF export gates, profile invalidation, session isolation, Interview Setup,
voice controller/UI lifecycle, completed-transcript feedback handoff, real API
adapters under mocked HTTP, retries, responsive layouts and preview isolation.
Mocks do not prove real microphone, provider audio or feedback quality.

## Real acceptance remains incomplete

The [original human run](2026-10-24-voice-interruption-investigation.md) had
interrupted playback and `unissued_question`. One substantive answer and question
advance were saved. Timer completion and a real feedback report matching the
canonical transcript revision are partial successes only.

The [controlled comparison](2026-10-24-controlled-voice-comparison.md) captured
complete headphone playback and a speaker-only false VAD interruption while the
user was silent. Provider speech-start preceded audio clear/cancellation with
`turn_detected`; disputed ASR text followed the cutoff. Speaker pickup is strongly
supported, but raw source audio was not captured. This comparison did not
reproduce `unissued_question` or exercise a complete answered interview.

Coordinate the interruption policy and the independently reproduced response
correlation defect with Luke before changing his implementation. Preserve the
unissued-output guard. Re-run targeted regressions and a real human end-to-end
interview after any agreed repair. The PR should stay **Draft** pending this work.

## Publication access check

At preparation, a non-mutating `git push --dry-run` was rejected by GitHub with
HTTP 403: local Git account `mioyokota-ctrl` lacked write access to
`tuilachit/Advanced-AI-Assignment3`. The GitHub connector independently reported
read-only access for `yumyum-coder`; its search found no existing PR for this
feature branch. Publication needs authorized repository access. This record is
not a claim that a branch was uploaded or a PR created.
