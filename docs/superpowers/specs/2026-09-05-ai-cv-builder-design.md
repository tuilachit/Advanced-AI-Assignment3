# AI-Powered CV Builder — Engineering Design

**Assessment:** 43007 Advanced Artificial Intelligence, Assessment 1  
**Design date:** 5 September 2026  
**Status:** Approved in conversation; awaiting written-spec review  
**Delivery model:** Locally runnable React application with a Python API

## 1. Purpose and success criteria

The system turns a user's natural-language introduction and follow-up answers into a confirmed, reusable profile. It retrieves the three most relevant jobs from the supplied nine-record corpus, generates an editable CV for a selected job using only confirmed facts, and exports a polished PDF. The same profile can produce a second job-specific CV, and different users must remain isolated.

Success has two dimensions:

1. **Assessment quality:** the complete user-to-PDF flow works reliably; agent decisions, tool calls, Observations, retrieval evidence, state updates, and failures are inspectable; all report claims are supported by actual evidence.
2. **Engineering ownership:** the student can explain the architecture, justify design decisions, predict expected behaviour, read and modify the implementation, diagnose failures, and verify each completed slice.

The application must not invent personal facts, job facts, employers, qualifications, technologies, experience, achievements, or numerical results.

## 2. Scope

### 2.1 Included

- Multiple independent temporary user sessions
- Natural-language introductions and follow-up answers
- Structured profile extraction, review, correction, and confirmation
- A bounded model-controlled tool-calling loop
- Semantic retrieval over all nine supplied jobs
- Top-three job results with unique `document_id` values and exact supporting excerpts
- Matched profile evidence and missing job requirements shown separately
- Structured, grounded CV generation
- CV editing, validation, preview, and PDF export
- Two CVs from one stable confirmed profile
- Cross-user isolation
- Development Prompt Record and evaluation evidence
- Automated and live-model tests

### 2.2 Excluded

- Deployment
- User accounts and authentication
- Persistent cloud storage or a database
- Supabase
- External job searching or scraping
- Changes to the supplied job records
- Training or fine-tuning a model
- Multi-agent orchestration
- Features unrelated to the assessment workflow

## 3. Technology choices

### 3.1 Frontend

- React with TypeScript
- Vite for local development and production builds
- A dedicated React PDF renderer for downloadable CVs
- Typed API client contracts generated or maintained from backend schemas

### 3.2 Backend

- Python with FastAPI
- Pydantic models for request, response, domain, Action, and Observation schemas
- A provider interface with an OpenAI implementation for tool calling, structured generation, and embeddings
- NumPy-based cosine similarity for transparent ranking
- In-memory session storage keyed by unguessable UUIDs

Model and embedding identifiers are runtime configuration. They are not embedded in domain logic. Provider secrets remain in a backend-only `.env` file and are never sent to React.

### 3.3 Data and generated files

- `data/jobs.jsonl` is the read-only retrieval corpus.
- `data/student_introductions.jsonl` supplies five controlled test introductions.
- `data/student_profiles.jsonl` supplies the corresponding expected confirmed facts.
- Embedding caches are derived data stored under an ignored cache directory and regenerated when the job-data hash or embedding-model identifier changes.
- Live user profiles exist only in backend memory and disappear when the server stops.

## 4. Repository structure

The current Advanced AI workspace is the repository root.

```text
frontend/                 React + TypeScript + Vite
backend/
  app/
    api/                  FastAPI routes
    models/               Pydantic domain models
    repositories/         Job and session access
    services/             Profile, agent, retrieval, CV, validation
    tools/                Model-callable tools
    providers/            Model and embedding adapters
  tests/
data/                     Supplied read-only JSONL files
tests/                    Cross-system and end-to-end tests
evidence/
  prompts/
  agent/
  retrieval/
  system_tests/
  failures/
sample_cvs/               Three verified sample PDFs
docs/                     Architecture and design documents
scripts/                  Setup, verification, and packaging
README.md
.env.example
.gitignore
```

Generated build output, virtual environments, dependency directories, model caches, real `.env` files, temporary visual-companion files, and final distribution archives are excluded from source control.

## 5. Architecture and responsibility boundaries

```text
React interface
    |
    | typed HTTP requests with session UUID
    v
FastAPI API layer
    |
    +-- Session repository
    +-- Profile service and profile tool
    +-- Bounded agent controller
    +-- Retrieval service and retrieval tool
    +-- Match and missing-requirement analysis
    +-- CV generation and grounding validation
    +-- Evidence recorder
    |
    v
Read-only JSONL data + temporary memory + ignored derived cache
```

React owns presentation and user interaction. FastAPI owns authoritative session state, provider secrets, state transitions, validation, and AI orchestration. Domain services do not depend on React or HTTP and can be tested directly.

## 6. Domain models

### 6.1 Confirmed facts and profile

Each fact has:

- Stable `fact_id`
- Category and field path
- Structured value
- Source turn ID
- Source type: introduction, follow-up, or explicit user correction
- Confirmation status

The profile covers:

- Contact details: name, email, phone, location, and links as applicable
- Education
- Technical skills
- Evidence supporting each skill
- Experience
- Projects
- Activities or achievements
- Target roles and job goal
- Availability and work rights when provided

A category may be complete with an explicitly confirmed empty value. For example, a student can confirm that they have no employment experience. Completeness means the category was addressed, not that it contains an impressive claim.

Each confirmation creates an immutable `profile_version`. A material new fact introduced later creates a new draft and requires reconfirmation.

### 6.2 Session

Each `SessionState` contains:

- `session_id`
- Current workflow state
- Draft profile and confirmed profile version
- Conversation turns
- Agent trace
- Retrieval runs
- CV documents
- Last recoverable error

No service may read another session unless that session ID is explicitly provided and resolved by the session repository.

### 6.3 Jobs and retrieval

`Job` mirrors the supplied fields without inventing missing values. `RetrievalResult` contains the exact `document_id`, title, similarity score, exact source excerpt, matched fact references, and missing requirements.

### 6.4 CV document

Each CV has:

- Unique `cv_id`
- Target job `document_id`
- Source `profile_version`
- Structured sections
- Claim-level profile fact references
- Generated and edited timestamps
- Validation state

Separate CV documents are retained when the target job changes. The confirmed profile is not rewritten to suit a job.

## 7. Workflow state machine

```text
collecting_profile
    -> profile_review
    -> profile_confirmed
    -> jobs_retrieved
    -> job_selected
    -> cv_draft
    -> cv_validated
    -> pdf_exported
```

Rules:

- Profile facts may be added or corrected during `collecting_profile` and `profile_review`.
- Only the user can confirm a profile.
- Job retrieval is rejected before confirmation.
- CV generation is rejected until one retrieved job is selected.
- Export is rejected while CV validation errors remain.
- Changing the selected job creates another CV from the same confirmed profile version.
- Introducing a new factual claim returns the profile to review and reconfirmation.
- Every transition is recorded with a timestamp and trace ID.

## 8. Agent and tool-calling design

The agent uses a transparent controller rather than a large orchestration framework. On each step, the backend supplies current state, permitted actions, system instructions, and relevant user input. The model selects one permitted Action. The backend validates it, executes the associated Python tool, records the Observation, updates state, and either continues or stops.

The loop allows at most six tool steps per user request. Reaching the limit produces a recoverable stopped state with the full trace preserved.

### 8.1 System/user separation

- System instructions define the model's role, allowed evidence, tool rules, grounding constraints, and output schema.
- User introductions and answers remain separate user content.
- The current structured state is passed as application context and cannot override system constraints.

### 8.2 Core tools

#### `update_profile`

Accepts structured facts extracted from the current user message. It records provenance and returns an Observation containing updated fields, unresolved categories, and the current workflow state. It cannot confirm the profile.

#### `retrieve_jobs`

Accepts a confirmed profile version and uses the backend's deterministic query builder. It returns exactly three unique ranked jobs with scores and exact excerpts. It rejects unconfirmed profiles.

#### `generate_cv`

Accepts one confirmed profile version and one selected retrieved job. It returns structured CV sections and claim-level source references. It cannot access another session.

### 8.3 Agent outcomes

The validated outcome is one of:

- Ask one useful follow-up question
- Update the draft profile
- Present the profile for review
- Retrieve jobs
- Generate a CV
- Return a final answer
- Stop with a clear error

## 9. Retrieval design

### 9.1 Job indexing

For each of the nine records, the index text combines:

- `document_id`
- Title
- Description
- Job type when present
- Location

Salary and benefits are displayed but excluded from the main semantic query so they do not dominate relevance.

The service creates one embedding for every full job record. Exact description sentences are also embedded so the service can select a high-relevance supporting sentence without paraphrasing it. Embeddings are cached using the source-data hash and model identifier.

### 9.2 Profile query

The query builder deterministically combines confirmed:

- Target roles
- Education
- Technical skills
- Skill evidence
- Project descriptions
- Relevant experience

The model does not freely write the retrieval query. This keeps retrieval reproducible and prevents unsupported content from entering search.

### 9.3 Ranking and evidence

The system embeds the query, computes cosine similarity against all nine job embeddings, sorts descending, removes duplicate IDs, and returns the top three. The supporting excerpt must be an exact substring of the corresponding original job description.

Retrieval relevance and eligibility are separate. A semantically related senior job may be retrieved while its experience or education requirements are honestly listed as missing.

### 9.4 Evaluation

Expected relevant jobs and reasons are written for all five supplied profiles before the first live retrieval run. Results are then compared against those frozen expectations. Predictions are not rewritten after results are observed.

## 10. Match analysis and CV grounding

Matched skills and missing requirements are derived from the confirmed profile and selected job description. Every match references one or more confirmed `fact_id` values and an exact job-description excerpt. Every missing requirement references job evidence and states only that the confirmed profile does not demonstrate it.

CV generation returns JSON rather than HTML. Each generated claim contains its supporting profile fact IDs. Validation includes:

- All referenced facts exist in the selected profile version.
- No referenced fact belongs to another session.
- Organisations, qualifications, technologies, dates, and numbers are checked against confirmed source values.
- Missing requirements cannot be used as candidate claims.
- A structured model-based grounding review runs separately from generation.
- Uncertain or unsupported claims block export and require user resolution.

Automated validation reduces risk but is not presented as a proof of factual correctness. The user reviews and confirms the final CV.

## 11. React user experience

The approved interaction model is a guided workflow with four visible stages:

1. **Profile:** conversation beside a structured draft and confirmation controls.
2. **Job matches:** top-three ranked jobs with IDs, scores, exact excerpts, matched evidence, and missing requirements.
3. **CV studio:** editable structured fields beside a live CV preview.
4. **Evidence:** inspectable state, Actions, tool executions, Observations, and guards.

The interface shows one primary task at a time and visible progress through the workflow. Evidence remains available without dominating the normal user journey.

CV editing supports wording changes, section reordering, hiding irrelevant items, restoring generated content, validating edits, and exporting. Editing invalidates the previous validation result. New factual content must be added to the profile and reconfirmed.

The PDF is rendered from the same structured CV used by the on-screen preview. Missing requirements appear in the application but not as negative statements in the PDF.

## 12. API surface

The initial API surface is:

- `POST /api/sessions` — create an isolated session
- `GET /api/sessions/{session_id}` — read current state
- `POST /api/sessions/{session_id}/messages` — process an introduction or follow-up answer
- `PUT /api/sessions/{session_id}/profile` — apply explicit user corrections
- `POST /api/sessions/{session_id}/profile/confirm` — confirm and version the profile
- `POST /api/sessions/{session_id}/jobs/retrieve` — run top-three retrieval
- `POST /api/sessions/{session_id}/jobs/{document_id}/select` — select a retrieved job
- `POST /api/sessions/{session_id}/cvs` — generate a structured CV
- `PUT /api/sessions/{session_id}/cvs/{cv_id}` — save user edits
- `POST /api/sessions/{session_id}/cvs/{cv_id}/validate` — validate grounding and enable export
- `GET /api/sessions/{session_id}/trace` — inspect Actions and Observations

PDF creation occurs in React only after the backend returns a valid CV state. Any subsequent edit disables export until validation runs again.

## 13. Failure handling and privacy

The system fails visibly, preserves valid state, and never fabricates a fallback result.

- An invalid model response is rejected and retried once with schema feedback.
- A second invalid response stops safely and preserves the trace.
- An embedding failure returns an explicit retrieval error rather than a guessed ranking.
- Duplicate retrieval IDs are rejected if three unique results cannot be formed.
- Malformed supplied data fails during startup with the file and record identified.
- An unsupported CV claim blocks export.
- A PDF-rendering failure preserves the edited CV for retry.
- A lost or unknown session produces a clear session error.

Real contact information is excluded from routine diagnostic logs. Evidence uses synthetic profiles. `.env` files, keys, tokens, dependency directories, caches, and temporary files are excluded from source control and submission packages.

## 14. Testing strategy

### 14.1 Unit tests

- JSONL loading and schema validation
- Profile completeness and explicitly empty categories
- State-transition guards
- Session isolation
- Retrieval sorting and deduplication
- Exact excerpt validation
- CV fact-reference validation
- Unsupported entity and numerical-claim detection
- Step-limit behaviour

### 14.2 Integration tests

A controlled fake provider makes agent tests deterministic:

- Introduction to profile Action and Observation
- Incomplete profile with at least two useful follow-up turns
- Complete profile with no unnecessary question
- Profile confirmation before retrieval
- Top-three retrieval response shape
- Selected job to grounded CV
- Invalid response, one retry, and recovery
- Repeated invalid response and safe stop
- Cross-session access rejection

Mocked results are clearly separated from live-model evidence.

### 14.3 End-to-end evaluation

For all five supplied profiles:

1. Freeze expected relevant jobs and reasons before retrieval.
2. Start from the supplied introduction.
3. Provide follow-up answers from the corresponding synthetic confirmed profile.
4. Review and confirm the generated profile.
5. Retrieve and record the top three jobs.
6. Compare expected and actual results.
7. Generate, validate, edit, and export a CV.

The evaluation also includes:

- At least one two-follow-up incomplete-profile run
- At least one complete-profile run without unnecessary questions
- Two job-specific CVs from one profile
- One CV from a second user
- An additional unseen profile
- A cross-user isolation test
- A genuine observed failure, targeted repair, retest, and regression check
- Three visually and structurally inspected sample PDFs

## 15. Evidence and Prompt Record

Every important implementation slice records:

- Development goal
- Exact prompt given to the coding agent
- Proposed change
- Student decision and justification
- Expected behaviour
- Verification method
- Actual result
- Next improvement

Agent evidence records Action, Python tool/function execution, Observation, state before and after, timestamps, and stop reason. Retrieval evidence records the query text, expected jobs, complete ranked top three, scores, IDs, and exact excerpts.

Only observed tests and features may be described as working. Missing evidence is marked explicitly rather than reconstructed or invented later.

## 16. Packaging

A deterministic packaging script creates:

```text
A1_<studentID>.zip
  A1_Report_<studentID>.pdf
  A1_Demo_<studentID>.mp4
  A1_Code_<studentID>.zip
```

The code archive contains source, supplied job data, README, pinned dependencies and lockfiles, placeholder configuration, five test profiles and results, architecture diagram, Prompt Record, and three sample CV PDFs. It excludes credentials, `.env` files, dependency folders, caches, model files, temporary files, and unrelated materials.

## 17. Acceptance criteria

The design is implemented successfully when:

- A new user can complete the introduction-to-PDF workflow without editing source code.
- An incomplete profile produces at least two useful follow-up turns in one recorded test.
- A complete profile produces no unnecessary question.
- The user reviews and confirms the profile before retrieval.
- All nine jobs are embedded and three unique jobs are returned with exact evidence.
- Expected-job predictions are frozen before live retrieval.
- Every CV claim is linked to confirmed profile evidence or blocked for review.
- Matched skills and missing requirements remain separate.
- Changing target jobs preserves the confirmed profile and produces meaningfully different CVs.
- Two users remain isolated in automated and live tests.
- The user can edit, validate, preview, and export a readable PDF.
- Three sample PDFs are inspected.
- One failure and repair are demonstrated honestly.
- Automated, mocked, and live evidence are clearly distinguished.
- Setup instructions reproduce the local application.
- Final archives contain the required files and no secrets.

