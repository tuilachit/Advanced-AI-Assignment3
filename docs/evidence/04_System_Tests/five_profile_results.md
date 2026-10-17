# Five-Profile Results

## Automated foundation

The deterministic suite currently verifies session isolation, state transitions, job-data validation, retrieval ordering, exact excerpts, tool limits, provider configuration, claim provenance, validation hashes, API errors, CORS, guided UI stages, export re-locking and provider failure recovery.

## Live evaluation table

| Profile | Variation | Expected primary job | Actual top three | Follow-up turns | CV validation | PDF | Status |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| `student_profile_01` | Software/API and applied AI projects | `graduate_ai_engineer` | `graduate_ai_engineer`, `agentic_ai_engineer`, `agentic_ai_data_scientist` | N/A: imported confirmed facts | Initial: blocked for skills described as experience; rerun 1: no issues | Export gate passed on rerun; no PDF rendered | Expected primary ranked 1 |
| `student_profile_02` | NLP, retrieval and classification | `rag_agent_engineer` | `graduate_ai_engineer`, `nlp_multimodal_ml_engineer`, `agentic_ai_data_scientist` | N/A: imported confirmed facts | Initial: no issues | Export gate passed; no PDF rendered | Expected primary outside top 3 |
| `student_profile_03` | Analytics and ambiguous data/software goal | `recommendation_systems_ml_engineer` | `graduate_ai_engineer`, `agentic_ai_data_scientist`, `nlp_multimodal_ml_engineer` | N/A: imported confirmed facts | Initial: blocked for unsupported graduation; rerun 1: no issues | Export gate passed on rerun; no PDF rendered | Expected primary outside top 3 |
| `student_profile_04` | Networking, support and ambiguous security goal | `trust_safety_ml_engineer` | `graduate_ai_engineer`, `computer_vision_engineer`, `agentic_ai_engineer` | Separate [agent test](../02_Agent/follow_up_question_test.md) | Initial: no issues | Export gate passed; no PDF rendered | Expected primary outside top 3 |
| `student_profile_05` | Cadetship, backend, tests and agent project | `agentic_ai_engineer` | `graduate_ai_engineer`, `agentic_ai_engineer`, `agentic_ai_data_scientist` | N/A: imported confirmed facts | Initial: blocked for backend headline without supporting citation; rerun 1: no issues | Export gate passed on rerun; no PDF rendered | Expected primary ranked 2 |

Observed on 2026-09-07 with `gpt-5.6-luna` and `text-embedding-3-small`. The supplied-five initial artifact and three-profile rerun are retained under [live records](../06_Live_Evaluation/records/). No failures were overwritten. The runner's `exported` value records the backend export gate/state transition; it does not mean a browser rendered or downloaded a PDF.

The frozen primary prediction matched top 1 for 1/5 supplied profiles and appeared in the top 3 for 2/5. These are six-profile development observations, not an unbiased benchmark. All supplied profiles ranked the general graduate AI role first. A plausible explanation is the shared computing degree and broad Python/project vocabulary, while the predictions emphasised specialisation; this explanation is an inference, not a causal ablation. Predictions and retrieval logic were not changed after seeing the results.

## Additional unseen profile

`unseen_profile_01` returned `computer_vision_engineer` (0.589143), `graduate_ai_engineer` (0.492901), and `nlp_multimodal_ml_engineer` (0.426580). The expected primary ranked first. CV validation returned no issues and the backend export gate passed on the initial run. Combined with the five supplied profiles, frozen primary top-1 agreement was 2/6 and top-3 inclusion was 3/6. Exact queries, scores, excerpts and generated CVs are retained in the records linked from the [live run report](../06_Live_Evaluation/2026-09-07-live-run.md).

## Post-reranker rerun — 2026-09-09

The same five supplied profiles were rerun after the evidence-aware reranker was added. This did
not replace the initial run or alter the frozen expectations. Each selected CV had zero validation
issues and passed the backend export gate; no live PDF was rendered by this service-side runner.

| Profile | Expected primary | Actual top three | Status |
| --- | --- | --- | --- |
| `student_profile_01` | `graduate_ai_engineer` | `graduate_ai_engineer`, `agentic_ai_data_scientist`, `rag_agent_engineer` | Expected primary ranked 1 |
| `student_profile_02` | `rag_agent_engineer` | `graduate_ai_engineer`, `agentic_ai_data_scientist`, `agentic_ai_engineer` | Expected primary outside top 3 |
| `student_profile_03` | `recommendation_systems_ml_engineer` | `graduate_ai_engineer`, `agentic_ai_data_scientist`, `nlp_multimodal_ml_engineer` | Expected primary outside top 3 |
| `student_profile_04` | `trust_safety_ml_engineer` | `agentic_ai_engineer`, `graduate_ai_engineer`, `computer_vision_engineer` | Expected primary outside top 3 |
| `student_profile_05` | `agentic_ai_engineer` | `graduate_ai_engineer`, `agentic_ai_engineer`, `agentic_ai_data_scientist` | Expected primary ranked 2 |
| `unseen_profile_01` | `computer_vision_engineer` | `computer_vision_engineer`, `graduate_ai_engineer`, `trust_safety_ml_engineer` | Expected primary ranked 1 |

Top-1 agreement remained 2/6 and top-3 inclusion was 4/6. These remain development observations:
the vision profile is a regression case, not a newly held-out benchmark. See the new [five-profile](../06_Live_Evaluation/records/post-reranker-2026-09-09/supplied-five/) and [vision](../06_Live_Evaluation/records/post-reranker-2026-09-09/unseen/) records.
