# Evidence-Aware Job Reranking — Design

**Assessment:** 43007 Advanced Artificial Intelligence, Assessment 1  
**Design date:** 9 September 2026  
**Status:** Approved in conversation; awaiting written-spec review

## Purpose

The existing retriever embeds one concatenated confirmed profile against each
job title and full description, ranks by cosine similarity, and only then
calculates evidence gaps. This is deterministic and useful for broad recall,
but it lets a broad graduate AI job dominate narrow evidence such as a RAG,
recommendation, trust-and-safety, or computer-vision project.

This change keeps embedding retrieval as the candidate-recall stage and adds a
deterministic, evidence-aware reranking stage. The final rank must be
explainable from confirmed candidate facts and supplied job text. It must not
infer personality, potential, seniority, work rights, eligibility, or facts
absent from the profile.

## Decision and non-goals

The primary ranking goal is **specialisation relevance**, not immediate
eligibility. A role can rank highly because a candidate's confirmed project or
skills match its domain while mandatory qualifications remain visible as
separate evidence gaps. The system must never hide those gaps or state that a
candidate is eligible.

This does not add a second model call, train a model, alter supplied records,
or make a rule that favours a role simply because the candidate named it. It
does not replace the existing requirement parser or semantic-audit/export
gates.

## Architecture

```text
confirmed profile facts
        |
        +--> broad embedding query ----------------------+
        |                                                |
        |                                           all nine jobs
        |                                                |
        |                                  cosine semantic shortlist
        |                                                |
        +--> declared skills, projects, education,       |
             explicit experience, target-role text       v
                                           structured job match profile
                                                     |
                                      deterministic evidence reranker
                                                     |
                                top three + score breakdown + explanation
```

The embedding stage remains the only provider-backed ranking operation and
continues to cache the nine job vectors. The reranker is pure Python and runs
only over the embedding shortlist (initially all nine supplied jobs because
the corpus is small). It receives the confirmed `ProfileDraft` and a derived
representation of each read-only `Job`.

## Structured job representation

At job-load time, derive an in-memory `JobMatchProfile`; do not rewrite
`data/jobs.jsonl`. It contains:

- `title_terms`: normalised meaningful terms from the title;
- `specialisation_terms`: terms from the title and role/responsibility text;
- `responsibility_terms`: terms from responsibility sentences;
- `mandatory_requirement_terms`: parsed mandatory requirements only;
- `optional_requirement_terms`: preferred/nice-to-have/desirable sections;
- `source_spans`: exact source sentences for every derived field.

The existing parser supplies mandatory requirements. A small section parser
will retain role/responsibility and optional spans for matching and
explanation. Unknown wording remains in the broad embedding text rather than
being silently discarded. The UI continues to show exact source excerpts, not
generated job summaries.

## Reranking algorithm

For each job, calculate five non-negative evidence components from confirmed
facts only:

| Component | Candidate evidence | Relative weight |
| --- | --- | ---: |
| Project/domain alignment | Project title, technologies and description | 0.40 |
| Technical-skill alignment | Declared skills or technical skills | 0.25 |
| Target-role alignment | Candidate's explicitly stated target role | 0.15 |
| Education alignment | Explicit course/discipline only | 0.10 |
| Explicit experience alignment | Stated role/experience text only | 0.10 |

Each component is a normalised phrase/token-overlap score against the relevant
structured job fields. Multiword terms are preserved where possible (for
example `computer vision`, `RAG`, `tool calling`, and `data structures`), with
the current alias handling retained. Generic terms such as `skill`, `project`,
`experience`, and `role` are excluded. Negative and aspirational facts remain
ineligible as match evidence.

The final score combines broad semantic relevance and the weighted evidence
score:

```text
final_score = 0.55 * cosine_semantic_score + 0.45 * evidence_score
```

The constants are initial defaults, not hidden tuning knobs. Their values and
all component values are returned in a score breakdown. Ties use the existing
stable `document_id` ordering. Mandatory requirements do not lower the score;
they remain visible through `missing_requirements`. Optional requirement terms
may contribute to a match explanation, but never to an eligibility claim.

## API and interface contract

Extend `RetrievalResult` with an additive `score_breakdown` object containing
the semantic score, each evidence component, and final score. Preserve the
existing `score` field as the final ranking score for backward compatibility.

Extend `match_reasons` so each reason names the fact field and the matching
specialisation signal, for example: `project: retrieval assistant -> RAG,
retrieval`. Frontend cards label the score as a **relevance score**, never as a
probability, suitability guarantee, or eligibility result. The existing
missing-requirements wording remains separate.

## Frozen offline baseline

Before changing ranking behaviour, commit a machine-readable baseline for the
five supplied profiles plus `unseen_profile_01` with:

- the old embedding-only top-three IDs and semantic scores;
- exact confirmed queries and job-data hash;
- the six frozen human predictions, labelled as development expectations;
- the old top-1/top-3 agreement summary;
- reranker component scores and ranking deltas after implementation.

The unseen vision profile is a regression case, not an independent held-out
benchmark: its contents and previous result have already been inspected. A
future genuinely unseen profile or marker-held input is required for an
unbiased generalisation claim. The supplied five are also a small development
set, so no threshold may be represented as a production-quality metric.

The baseline's first purpose is reproducibility: it must show exactly what
changed and prevent accidental degradation of the current correct graduate-AI
and computer-vision results. Its second purpose is diagnostic comparison; it
does not authorise changing the frozen expectations after observing outcomes.

## Tests and verification

Tests precede implementation and cover:

1. structured job parsing retains exact source spans and separates mandatory
   from optional requirements;
2. a project-specific RAG or vision fact raises the appropriate specialised
   job's evidence component without treating a missing master's degree or
   years requirement as evidence;
3. declared skills do not become work experience, aspirations/negatives do not
   score, and unknown facts do not contribute;
4. deterministic final ordering, tie-breaking, score-breakdown arithmetic,
   and unchanged session isolation;
5. frozen baseline generation and comparison against the current
   embedding-only result;
6. backend/API schema and frontend contract checks display the breakdown
   without implying eligibility.

Verification is offline first: backend tests, Ruff, mypy, frontend contract,
unit tests, lint, type checks, build, and relevant browser tests. The
before/after baseline and every regression must be reviewed before requesting
permission for any billable live OpenAI rerun.

## Success criteria

- The broad embedding candidate set remains deterministic and cached.
- Every changed rank has a fact- and source-backed explanation.
- A broad job cannot win solely because generic degree/Python vocabulary
  overwhelms explicit specialisation evidence.
- The computer-vision regression remains top-ranked for its direct OpenCV /
  classifier evidence unless a documented, evidence-backed reason says
  otherwise.
- No profile is declared eligible, experienced, senior, graduated, or
  professionally employed without confirmed evidence.
- Frozen baseline artifacts, tests, and documentation state both improvements
  and regressions honestly.
