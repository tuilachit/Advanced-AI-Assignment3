# Follow-up Question Test

## Planned incomplete-profile case

- **Profile:** `student_profile_04`
- **Supplied introduction:** `I study Computing Science at UTS. I have done some networking and software projects and I work in IT support. I am interested in security, but I have not yet decided which technical role fits me.`
- **Why incomplete:** The target role is ambiguous, and the introduction does not provide contact details or a specific achievement.
- **Minimum success condition:** At least two useful, non-repeated follow-up turns before confirmation.
- **Expected first priority:** Clarify the target role without inventing one.
- **Expected next priority:** Ask for another missing category such as contact details, a project detail or an achievement.
- **Stop rule:** Once the required core facts are unambiguous, summarise the draft and wait for explicit user confirmation.

## Planned complete-profile case

- **Profile:** `unseen_profile_01` in `../04_System_Tests/test_profiles/unseen_profile_01.json`.
- **Minimum success condition:** Capture the complete supplied facts without an unnecessary follow-up question.

## Actual live comparison

Observed on 2026-09-07 with `gpt-5.6-luna`. Exact messages are in each timestamped artifact; tool names, supplied arguments, observations and saved draft facts are in `service-evidence.json` alongside the exact prompt snapshot.

| Attempt | Actual behaviour | Reviewed outcome |
| --- | --- | --- |
| Complete, initial | Saved the full supplied unseen profile, summarised it and requested explicit confirmation without an extra information question | Passed; facts remain drafts in `profile_review` |
| Incomplete, initial | Asked name/contact, then asked the same name question twice | Failed manual quality review although the original runner returned 0; its question-count heuristic missed repetition and its reply helper missed supplied names |
| Incomplete, rerun 1 | Clarified target role, then requested full name/contact with “Please provide…” | Valid follow-up incorrectly rejected by the runner's question-mark heuristic; retained exit code 1 |
| Incomplete, rerun 2 | Clarified technical security direction; asked name/contact; then asked IT-support responsibilities and employer | Passed the minimum two distinct useful follow-up turns; no confirmation or retrieval attempted |

Final conversation excerpt, with actual model wording:

1. Assistant: `Which technical security direction interests you most: **SOC/security analyst, network security, penetration testing, cloud security, security engineering**, or another role?`
2. Factual reply: `My target role is Cybersecurity Intern.`
3. Assistant: `What name and contact details would you like included on your CV (email, phone, LinkedIn, or portfolio)?`
4. Factual reply: `My supplied name is Noah Ibrahim. No contact details are supplied in this synthetic profile.`
5. Assistant: `What were your main responsibilities in your IT support role, and what was the employer or organisation?`

The final question is useful but the bounded scenario stops here after its two factual replies; it does not demonstrate full profile completion. No absent contact details were invented. The initial conversation remains a failure, and the punctuation-only rejection remains a harness defect in the evidence history.

Records: [complete](../06_Live_Evaluation/records/complete-agent-initial/), [incomplete initial](../06_Live_Evaluation/records/incomplete-agent-initial/), [rerun 1](../06_Live_Evaluation/records/incomplete-agent-rerun-1/), [rerun 2](../06_Live_Evaluation/records/incomplete-agent-rerun-2/).
