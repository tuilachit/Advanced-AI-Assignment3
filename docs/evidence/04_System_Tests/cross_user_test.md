# Cross-User Test

## Automated result

`test_sessions_are_uuid_keyed_and_isolated` creates two UUID sessions, updates only the first session with Maya's name and confirms that the second session still has no facts. Unknown IDs raise `SessionNotFoundError` rather than creating a session silently.

The complete API test addresses every resource through `/api/sessions/{session_id}/...`. The React workspace keeps the current session ID internally while presenting a non-technical “Personal workspace” label, and the browser failure test confirms that a provider failure does not replace or lose that session.

## Sample-PDF result

The first two sample PDFs cite facts only from `student_profile_01`; the third cites facts only from `student_profile_02`. The sample-data test validates every claim reference against the confirmed fact-ID set for that sample.

## Live result

The 2026-09-07 live runner created two active sessions in the same application service instance, labelled `student_profile_01` and `student_profile_02` in the redacted evidence. Each retained only its imported profile source. Both retrieved their own top three; every captured generated CV cited only facts present in that CV's input profile. UUIDs and provider response IDs are not needed in the retained artifacts.

| Attempt | Session isolation | Profile 01 CV | Profile 02 CV |
| --- | --- | --- | --- |
| Initial | Passed | Blocked: skills described as experience | Validation clear; export gate passed |
| Rerun 1 | Passed | Blocked: unsupported developer identity and implied sole project ownership | Validation clear; export gate passed |
| Rerun 2 | Passed | Validation clear; export gate passed | Validation clear; export gate passed |

Both failures and their generated text remain under [initial](../06_Live_Evaluation/records/session-isolation-initial/), [rerun 1](../06_Live_Evaluation/records/session-isolation-rerun-1/) and [rerun 2](../06_Live_Evaluation/records/session-isolation-rerun-2/). Generation prompts were tightened after deterministic red tests; the semantic audit and export hash gate were not weakened.

This is a sequential two-session service test. It does not establish concurrency, multi-process persistence or authenticated browser isolation. The separate mocked Playwright browser isolation check also passed; no live browser screenshots or live PDF downloads were created in this evaluation.

## Post-reranker rerun — 2026-09-09

The current system repeated the sequential service test with `student_profile_01` and
`student_profile_02`. Each session retained only its imported profile source, retrieved its own
top three and produced a zero-issue CV that passed the export gate. The retained
[post-reranker isolation record](../06_Live_Evaluation/records/post-reranker-2026-09-09/session-isolation/) preserves the same limitation: it is not a concurrency or authenticated-browser claim.
