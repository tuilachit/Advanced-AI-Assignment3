# PDF sample review

Review date: 9 September 2026

These are offline, deterministic examples generated from the supplied synthetic profiles. They are not live-model evaluation results. The same `CVPdfDocument` renderer powers the application's gated download action and the sample generator.

The reader-facing output uses a black-only, single-column Harvard-style layout: a centred name
and headline, a confirmed-contact line when contact facts exist, conventional section ordering,
and restrained rules. Internal target-job IDs and evidence labels are not printed in the PDF; the
target document IDs remain recorded in this evidence table and the audit view.

| File | Supplied profile | Target job | Structural check | Visual check |
| --- | --- | --- | --- | --- |
| `sample-01-maya-chen-graduate-ai.pdf` | `student_profile_01` | `graduate_ai_engineer` | 1 A4 page; 102 extracted words; no internal IDs | Pass - no clipping, overlap or unreadable text |
| `sample-02-maya-chen-agentic-ai.pdf` | `student_profile_01` | `agentic_ai_engineer` | 1 A4 page; 103 extracted words; no internal IDs | Pass - no clipping, overlap or unreadable text |
| `sample-03-liam-patel-rag-ai.pdf` | `student_profile_02` | `rag_agent_engineer` | 1 A4 page; 83 extracted words; no internal IDs | Pass - no clipping, overlap or unreadable text |

## Evidence gates exercised

- The sample-data test requires exactly three samples.
- The first two samples must reuse one confirmed profile for two different target jobs, while the third must use another profile.
- Every claim must be marked verified.
- Every claim must cite at least one fact ID.
- Every cited fact ID must resolve to a confirmed fact from the same supplied profile.
- The renderer test requires a real PDF header and a non-trivial output buffer.
- `pypdf` confirmed A4 page metadata, extractable text and the absence of target-job IDs or the old `Target job evidence` label. Final PNGs were rendered at 144 DPI and visually inspected for spacing, clipping, overlap and legibility.

## Observed tooling issue

The bundled Poppler renderer reported a missing font configuration while rendering, but completed
the PNG output. Text extraction used the installed `pypdf` library, and each final sample was
rendered independently before inspection. The final files and review images were complete.
