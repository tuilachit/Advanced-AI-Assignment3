# Retrieval Results

## Method

`JobRepository` validates that `data/jobs.jsonl` contains exactly nine unique `document_id` values. `RetrievalService` builds a deterministic query from confirmed profile facts while excluding the user's name. It embeds each job's title and description once, caches those vectors in memory, embeds the query for broad recall, then applies a fixed evidence-aware reranker before using `document_id` as the tie-break. Each top-three item includes an exact sentence from the source description, supporting profile overlaps and mandatory requirements that have no confirmed evidence.

The evidence-gap check is deliberately conservative. It excludes optional sections, aspirations and negative statements; requires the full terms of conjunctive skills; checks real alternatives independently; and treats minimum/maximum experience duration and degree level as typed constraints instead of generic keyword overlap. Its output says only what the confirmed profile has not established, never whether the candidate is eligible.

Missing requirements are evidence gaps only. They do not automatically decide eligibility.

## Frozen embedding-only baseline provenance

[`embedding_baseline_2026-09-07.json`](embedding_baseline_2026-09-07.json) freezes the pre-reranker development evidence for the five supplied profiles and `unseen_profile_01`. It records the SHA-256 of [`data/jobs.jsonl`](../../../data/jobs.jsonl), `0f9403de41f2de0605bbbf6ef3faa3a81f265b7ec36938aea6c058ada723b461`, alongside the observed embedding-only top-three IDs and semantic scores copied from the timestamped [supplied-five source artifact](../06_Live_Evaluation/records/supplied-five-initial/2026-09-07-152935354411-supplied-five.json) and [unseen source artifact](../06_Live_Evaluation/records/unseen-initial/2026-09-07-153114169436-unseen.json).

This is pre-reranker development evidence. The previously viewed computer-vision profile is a regression case, not held-out evidence; the five supplied profiles are also development cases. The offline validator checks the frozen corpus hash, source-artifact paths, profile records, and ranked document IDs without making a provider request.

## Candidate pre-run predictions

These predictions are frozen as Luke's reviewed decisions before live retrieval.

| Profile | Primary expected `document_id` | Reason for prediction | Luke review |
| --- | --- | --- | --- |
| `student_profile_01` | `graduate_ai_engineer` | Python API, validation, testing and a tool-call agent align with a graduate applied-AI role | Approved before live retrieval on 2026-09-07 |
| `student_profile_02` | `rag_agent_engineer` | Retrieval-augmented assistant, LLM interest, Python and evaluation align semantically; experience eligibility is a separate gap | Approved before live retrieval on 2026-09-07 |
| `student_profile_03` | `recommendation_systems_ml_engineer` | Data cleaning, analysis, visualisation and search-result comparison align with recommendation/search experimentation | Approved before live retrieval on 2026-09-07 |
| `student_profile_04` | `trust_safety_ml_engineer` | Security interest, networking, Python, data structures and teamwork are the nearest graduate-level evidence | Approved before live retrieval on 2026-09-07 |
| `student_profile_05` | `agentic_ai_engineer` | Backend cadetship, testing, Docker/CI basics and a tool-call agent align with agentic workflow delivery | Approved before live retrieval on 2026-09-07 |
| `unseen_profile_01` | `computer_vision_engineer` | OpenCV/PyTorch image classifier and Docker evidence target computer vision despite likely experience gaps | Approved before live retrieval on 2026-09-07 |

## Deterministic retrieval checks

- Nine supplied jobs load successfully and duplicate IDs are rejected.
- Draft or mixed-status profile facts block retrieval.
- A fixed fake embedding test returns `job-a`, `job-b`, `job-c` in deterministic order.
- Exact excerpts are substrings of the corresponding job description.
- Job vectors are cached: two retrievals cause one job-embedding call and two query calls.
- Matched skills and missing requirements are returned separately.

## Offline reranking regression comparison

This is an offline regression comparison, not a new provider observation. The baseline column
copies the recorded embedding-only top three from 2026-09-07. The reranker column comes from
running the current `RetrievalService` with the fixed-vector fixture: the three recorded scores
are fixture coordinates, while each historically unobserved fourth-to-ninth job receives the
same synthetic coordinate immediately below recorded third place. The fixture therefore makes
the comparison repeatable without claiming that the six unrecorded historical scores are known.

In the rank-delta column, each entry follows the corresponding reranker item and shows its
recorded baseline position followed by its fixture position. `>=4` means only that the item was
outside the recorded baseline top three; it is not an observed historical rank.

| Profile | Embedding-only baseline top three | Fixed-vector reranker top three | Rank delta (baseline -> fixture) |
| --- | --- | --- | --- |
| `student_profile_01` | `graduate_ai_engineer` > `agentic_ai_engineer` > `agentic_ai_data_scientist` | `trust_safety_ml_engineer` > `rag_agent_engineer` > `computer_vision_engineer` | `>=4 -> 1`; `>=4 -> 2`; `>=4 -> 3` |
| `student_profile_02` | `graduate_ai_engineer` > `nlp_multimodal_ml_engineer` > `agentic_ai_data_scientist` | `graduate_ai_engineer` > `trust_safety_ml_engineer` > `agentic_ai_data_scientist` | `1 -> 1`; `>=4 -> 2`; `3 -> 3` |
| `student_profile_03` | `graduate_ai_engineer` > `agentic_ai_data_scientist` > `nlp_multimodal_ml_engineer` | `graduate_ai_engineer` > `agentic_ai_data_scientist` > `nlp_multimodal_ml_engineer` | `1 -> 1`; `2 -> 2`; `3 -> 3` |
| `student_profile_04` | `graduate_ai_engineer` > `computer_vision_engineer` > `agentic_ai_engineer` | `agentic_ai_engineer` > `healthcare_ml_engineer` > `graduate_ai_engineer` | `3 -> 1`; `>=4 -> 2`; `1 -> 3` |
| `student_profile_05` | `graduate_ai_engineer` > `agentic_ai_engineer` > `agentic_ai_data_scientist` | `graduate_ai_engineer` > `rag_agent_engineer` > `agentic_ai_engineer` | `1 -> 1`; `>=4 -> 2`; `2 -> 3` |
| `unseen_profile_01` | `computer_vision_engineer` > `graduate_ai_engineer` > `nlp_multimodal_ml_engineer` | `computer_vision_engineer` > `graduate_ai_engineer` > `trust_safety_ml_engineer` | `1 -> 1`; `2 -> 2`; `>=4 -> 3` |

The fixture arithmetic leaves `student_profile_03` unchanged. It preserves the first and third
positions for `student_profile_02`, moves `agentic_ai_engineer` from third to first for
`student_profile_04`, keeps `graduate_ai_engineer` first for `student_profile_05`, and retains the
first two vision-regression positions. For `student_profile_01`, all three reranked items come
from the tied synthetic remainder, so that row is especially unsuitable as a retrieval-quality
claim. These rank changes show what the deterministic evidence weights do under this regression
fixture; they do not establish improvement against unknown historical fourth-to-ninth scores.

## Post-reranker live evaluation — 2026-09-09

With fresh user approval, the current reranker was evaluated against the same five supplied
profiles and the existing computer-vision regression profile. The six expectations remained
unchanged; no ranking logic or expectation was tuned after observing this run. Every selected CV
had zero validation issues and passed the backend export gate. The gate records eligibility to
export; it does not mean a browser rendered or downloaded a PDF.

| Profile | Expected primary | Observed current top three | Expected position |
| --- | --- | --- | --- |
| `student_profile_01` | `graduate_ai_engineer` | `graduate_ai_engineer` > `agentic_ai_data_scientist` > `rag_agent_engineer` | 1 |
| `student_profile_02` | `rag_agent_engineer` | `graduate_ai_engineer` > `agentic_ai_data_scientist` > `agentic_ai_engineer` | outside top 3 |
| `student_profile_03` | `recommendation_systems_ml_engineer` | `graduate_ai_engineer` > `agentic_ai_data_scientist` > `nlp_multimodal_ml_engineer` | outside top 3 |
| `student_profile_04` | `trust_safety_ml_engineer` | `agentic_ai_engineer` > `graduate_ai_engineer` > `computer_vision_engineer` | outside top 3 |
| `student_profile_05` | `agentic_ai_engineer` | `graduate_ai_engineer` > `agentic_ai_engineer` > `agentic_ai_data_scientist` | 2 |
| `unseen_profile_01` | `computer_vision_engineer` | `computer_vision_engineer` > `graduate_ai_engineer` > `trust_safety_ml_engineer` | 1 |

Observed top-1 agreement was 2/6 and expected-job top-3 inclusion was 4/6. The latter is one
more development-case inclusion than the 2026-09-07 run; it is not an independent held-out
benchmark or a causal proof of retrieval improvement. Relevance is not eligibility.

The complete allowlisted records are retained in the [five-profile directory](../06_Live_Evaluation/records/post-reranker-2026-09-09/supplied-five/) and the [vision-regression directory](../06_Live_Evaluation/records/post-reranker-2026-09-09/unseen/).

## Live results

The approved live evaluation ran on 2026-09-07. The [five-profile results](../04_System_Tests/five_profile_results.md) report the unchanged frozen predictions against actual top-three IDs, including all disagreements and the additional unseen profile. Each scenario's timestamped outcome artifact retains exact scores and source excerpts; its allowlisted `service-evidence.json` supplement retains the exact profile query. These are processed service outputs, not raw provider objects.

Frozen primary top-1 agreement was 1/5 for the supplied profiles and 2/6 with the unseen profile; top-3 inclusion was 2/5 and 3/6 respectively. All supplied profiles ranked `graduate_ai_engineer` first. The unseen profile ranked the expected `computer_vision_engineer` first. The observed rankings were not used to change expectations or tune retrieval. See the [live report and record index](../06_Live_Evaluation/2026-09-07-live-run.md).
