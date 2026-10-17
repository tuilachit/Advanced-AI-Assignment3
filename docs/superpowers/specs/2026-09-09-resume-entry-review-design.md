# Resume Entry Review Design

## Purpose

Students often describe their work in short, informal sentences. The app should turn those
confirmed statements into professional, structured resume entries without inventing facts or
making the student approve opaque wording in the final CV only.

This design adds an explicit review layer between confirmed profile facts and job retrieval/CV
generation. It keeps the student’s original wording as the source of truth and gives the student
control over the polished resume representation.

## Scope

Included:

- Propose structured entries from confirmed profile facts.
- Let the student edit, remove, and explicitly approve those entries.
- Preserve field- and bullet-level links from every entry to its confirmed source facts.
- Generate job-specific CVs only from approved resume entries plus confirmed contact details.
- Invalidate dependent entries, matches, and CVs when source facts change.
- Add deterministic and semantic evidence checks, API support, UI coverage, and tests.

Excluded:

- A multi-CV archive or side-by-side comparison interface. The existing workflow continues to
  support selecting job A, generating a CV, then selecting job B and generating another CV from
  the same unchanged confirmed profile.
- Inference of missing dates, employers, titles, seniority, achievements, outcomes, metrics,
  qualifications, work rights, or eligibility.
- Persistent storage, authentication, or changes to the supplied job data.

## Design principles

1. Original student facts are the evidence authority. Proposed resume entries are derived,
   reviewable material and never replace or mutate those facts.
2. Professional wording means clearer structure and faithful rephrasing, not embellishment.
3. A student approves every resume entry before it can influence a CV.
4. The selected job tailors ordering and emphasis; job requirements never become student facts.
5. Evidence is visible in the review flow and auditable in the Evidence stage. Raw identifiers
   remain hidden from normal student-facing screens.

## Workflow

The session workflow becomes:

```text
collecting_profile
  -> profile_review
  -> profile_confirmed
  -> resume_entries_review
  -> resume_entries_approved
  -> jobs_retrieved
  -> job_selected
  -> cv_draft
  -> cv_validated
  -> pdf_exported
```

After confirming raw profile facts, the student asks the system to propose resume entries. The
student then reviews individual entries, editing or removing them as desired, and approves the
entries they want included. Job retrieval and CV generation are unavailable until the review
contains at least one approved substantive entry. Confirmed contact facts remain available for
the CV header and do not need a separate resume entry.

Changing a source fact marks each linked entry as `needs_review`, clears all approved-entry
eligibility, and invalidates retrieval results, selected job, CV, validation result, and export
state. The student must reconfirm the changed raw fact, regenerate or edit affected entries, and
approve them again.

## Data model

### Source facts

`Fact` remains the immutable provenance unit already held in `ProfileDraft`. A source fact has a
stable ID, source information, and a `draft` or `confirmed` status.

### Resume entries

Add a resume-entry model separate from `ProfileDraft`:

- `entry_id`: stable identifier.
- `kind`: `experience`, `project`, `education`, `skills`, or `achievement`.
- `heading`: concise reader-facing title, such as `Data Science Intern` or `Text classifier`.
- `organisation_or_context`: optional; present only when explicitly supported.
- `details`: small list of labelled display fields, for example `Technologies` or `Study`.
- `bullets`: one to three concise contribution or context statements.
- `source_fact_ids`: all facts supporting the entry.
- `field_source_fact_ids`: fact references for the heading/context and every detail/bullet,
  allowing granular deterministic checks.
- `status`: `proposed`, `approved`, or `needs_review`.

Every visible item must have at least one source fact ID. A reference may only point to a
confirmed fact. The schema must reject empty headings, blank bullets, unknown fact IDs, and
unconfirmed evidence.

The session holds `resume_entries` and a resume-entry revision. The CV model continues to use
claim-to-fact mappings so downstream CV validation preserves the assignment’s original evidence
contract.

## Proposal generation

Add a provider operation that accepts confirmed facts and produces a structured list of proposed
resume entries. Its schema must require citations for every field and bullet.

Generation instructions will require the model to:

- Prefer conventional resume structures over restating raw text.
- Use only facts expressly provided by the student.
- Distinguish a listed skill from practical experience.
- Preserve team context and stated contribution for group work.
- Use an employer, job title, date, metric, outcome, ownership, qualification, or seniority only
  when the source facts explicitly support it.
- Return no entry rather than fill a missing detail with a plausible guess.

Example transformation:

> Raw fact: “Completed a Data Science internship at Three Piece Marketing, conducting market
> research and analytics and identifying errors and failures in an AI chatbot for a client.”

becomes a proposed entry:

> **Data Science Intern — Three Piece Marketing**
> - Conducted market research and data analysis during a data science internship.
> - Investigated errors and failures in a client AI chatbot.

It cannot claim an accuracy improvement, a leadership role, a delivery outcome, or a metric that
the raw fact did not provide.

## Student experience

Add a `Resume entries` step between `Profile` and `Job matches`.

Each entry card shows:

- The polished conventional resume entry.
- A labelled `Based on what you told us` section containing the human-readable source fact values.
- Edit, remove, and approve controls.
- Clear `Proposed`, `Approved`, and `Needs review` status.

Students edit the displayed text, not source identifiers. Edited entries retain their cited facts
and are checked before approval. Removing an entry means it will not be used in the CV; it does
not erase the underlying profile facts.

The Evidence stage exposes the detailed entry-to-fact mappings and proposal/approval trace events
for assessment audit. The job-results and PDF views stay reader-facing and do not expose internal
document IDs or fact IDs.

## CV and two-job behaviour

Only approved resume entries and confirmed contact facts form the CV-generation input. The target
job may change headline wording, choose relevant approved entries, order entries, and select
evidence-supported bullets. It may not create a candidate fact or use a job requirement as
candidate evidence.

The current sequential two-job workflow remains: with the same unchanged approved entries, a
student can select one retrieved job and generate CV A, then select another retrieved job and
generate tailored CV B. Selecting a different job clears the active CV to prevent cross-job
export; an in-app archive/comparison screen is outside this change.

## Error handling

The application must return recoverable, plain-language errors for:

- proposing entries before a confirmed profile exists;
- approving an entry with unknown, deleted, draft, or unconfirmed evidence;
- generating a CV before at least one substantive entry is approved;
- provider failure or malformed structured output;
- editing a raw fact that has invalidated dependent entries;
- attempting to validate or export an outdated CV.

Two layers protect factual accuracy:

1. Deterministic validation checks source reference existence and confirmation status.
2. A separate semantic validator marks unsupported additions as blocking errors. A modest,
   evidence-grounded interpretive phrase may be a non-blocking warning, consistent with the
   existing CV wording policy.

## API and frontend contract

Add explicit API operations to propose entries, update one entry, approve one entry, and list
entry evidence through the session response. Update the generated OpenAPI schema and frontend
types from the backend contract; do not hand-maintain a divergent client-only type.

The session response becomes the single source of truth for entry statuses and allowed next
actions. The React navigation must disable Job matches and CV studio until the relevant review
criteria have been met.

## Tests and verification

Backend tests will prove that:

- proposals retain complete and valid provenance;
- unknown, deleted, draft, mismatched, and unconfirmed sources cannot be approved or reach a CV;
- raw-fact edits invalidate linked entries and all downstream artefacts;
- provider output with invented detail is rejected or blocked by validation;
- two selected jobs receive different CV documents from the same unchanged approved profile.

Frontend and browser tests will prove that:

- the review stage is correctly gated;
- the student can inspect raw wording, edit, remove, and approve an entry;
- job retrieval/CV generation are blocked before approval;
- invalidated entries display a clear recovery action;
- the complete desktop and mobile flow remains usable.

The final verification gate runs backend tests, Ruff, mypy, frontend contract generation/checking,
Vitest, ESLint, TypeScript checking, production build, Playwright, and a focused live provider
scenario before new assessment evidence is recorded.
