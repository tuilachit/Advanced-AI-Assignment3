# Rich-profile category regression repair

## Observed failure

A profile contained 16 extracted facts, including named experience fields, plural `projects`
and research entries. Confirmation returned 409 with `experience_or_project` missing because
the gate recognised only exact `experience` and `project` keys. Ranking likewise ignored
named work in its category-specific scores. The user's information was present; its labels
were interpreted inconsistently.

## Repair

- Added one bounded, deterministic category resolver shared by confirmation, query building,
  ranking, match explanations, skills/requirement checks and interview-feedback context.
- Kept individual field keys, fact IDs, values, sources and confirmation status unchanged.
  Multiple employers/projects are not collapsed into one update slot.
- Guided extraction toward stable category-prefixed keys and returned server-calculated
  `missing_fields` both in the initial agent context and after profile updates. Only the
  user can confirm a profile.
- Retained legacy aliases, including `projects`, `other_experience`, `technical_skills`
  and named research fields. Research is project evidence, not professional tenure.
- Excluded unknown, goal and private/contact labels from matching evidence. Confirmed
  queries retain all recognised facts deterministically; contact facts are excluded.
- Preserved draft/negation/aspiration safeguards and separate degree/professional-years
  checks. Matching still does not establish eligibility.

## Verification performed

New regression cases were run against the original implementation and reproduced the
confirmation failure and missing ranking evidence before applying the repair.

- 33 category regression cases cover named/plural fields, formatting aliases, machine-learning
  labels, separate score components, private/goal exclusions, identity boundaries,
  unconfirmed/aspirational/negative evidence, professional-years and degree gaps,
  deterministic queries, and a synthetic 16-fact extraction/revision scenario.
- One offline API regression exercises scripted extraction, confirmation, proposed-entry
  review/approval and three-job retrieval, checking fact IDs and work-evidence scores.
- One feedback regression checks inclusion of named work and exclusion of private/goal fields.
- Full backend suite: **596 passed**. Ruff and mypy passed.
- Frontend unit suite: **190 passed**. ESLint, TypeScript, OpenAPI contract check and production
  build passed. No public API schema migration was needed.
- Browser suite: **36 passed**, using an isolated frontend on port 5174 with the existing
  request fixtures. The temporary browser configuration was removed afterwards.
- A read-only snapshot of the affected real session was replayed in a separate local workflow:
  16 fact IDs preserved, zero missing categories, confirmation successful, all eight named
  work/research/project facts included in the query, and nonzero work/project scoring.
  No personal profile text is included in these test fixtures or this record.
- After the user approved clearing temporary sessions, the backend was restarted. Health
  and frontend requests returned 200. A synthetic eight-fact local API check confirmed
  successfully with all fact IDs preserved.

These checks made **no OpenAI requests**. They verify deterministic categorisation and
workflow behaviour, not a new live extraction, embedding ranking or microphone-quality run.
The existing local key remains backend-only; realtime configuration remains `gpt-realtime-2`.
