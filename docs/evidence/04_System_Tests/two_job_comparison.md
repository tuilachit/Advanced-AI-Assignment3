# Two Jobs for the Same User

## Offline reviewed comparison

Both PDFs use the same confirmed Maya facts from `student_profile_01`. The test rejects the sample set if the first two profile IDs differ or if their target job IDs are the same.

| Dimension | `graduate_ai_engineer` CV | `agentic_ai_engineer` CV |
| --- | --- | --- |
| Headline | Python, APIs and applied AI | Python workflows, testing and documentation |
| First detailed section | Selected projects | Technical skills |
| First project emphasis | Python service logic, SQL, endpoints, validation and tests | Bounded tool-call agent and recorded results |
| Second project emphasis | Tool selection and observations | Service logic, endpoint design and automated tests |
| Transferable experience label | Experience | Team and customer experience |
| Source facts | `student_profile_01` | `student_profile_01` |

Files:

- `output/pdf/sample-01-maya-chen-graduate-ai.pdf`
- `output/pdf/sample-02-maya-chen-agentic-ai.pdf`

The wording and ordering change, but neither CV adds metrics, employers, seniority or qualifications. This section describes the offline deterministic samples.

## Live comparison on 2026-09-07

The initial live run generated both requested jobs for the same confirmed `student_profile_01` facts. Both jobs were in the live top three. Both CVs passed semantic validation with zero issues and passed the backend export gate. No live PDF was rendered by this service-side runner.

| Dimension | `graduate_ai_engineer` | `agentic_ai_engineer` |
| --- | --- | --- |
| Headline | Bachelor of Computing Science; Python, REST APIs, SQL, Git and pytest | Bachelor of Computing Science candidate; broader eight-skill list |
| Section order | Education, Technical Skills, Projects, Experience | Same order, then Target Role |
| Project order | Team Course Planner, AI Coursework Prototype | Same order |
| Tool-call project | Concise description with prompt design, tool calling and JSON | Similar description, with explicit technologies label |
| Source IDs | Only `student_profile_01` fact IDs | Identical confirmed profile; only its fact IDs |

The live wording differs, but tailoring is modest: the agentic CV did not move the agent project ahead of the API project. Its extra Target Role section repeats the supplied Software Engineering Intern aspiration. The evidence supports two valid outputs for two jobs; it does not support a claim of strong changes to ordering or emphasis. No live rerun was performed for this already valid comparison.

See the [initial scenario directory](../06_Live_Evaluation/records/two-job-comparison-initial/) for the outcome artifact and `service-evidence.json`, which retains both complete generated CVs, exact query, and validation results.

## Post-reranker repair and rerun — 2026-09-09

The first post-reranker attempt retained the old hard-coded pair. Its second requested job,
`agentic_ai_engineer`, was no longer in `student_profile_01`'s current top three, so the backend
correctly rejected the selection. The failed artifact is retained rather than overwritten.

The evaluator was repaired to compare the first two jobs returned by the current retrieval result,
which respects the application rule that only retrieved jobs may be selected. The rerun compared
`graduate_ai_engineer` and `agentic_ai_data_scientist` for the same confirmed profile. Both CVs
had zero validation issues and passed the backend export gate. This proves two valid current-job
outputs, but does not establish strong tailoring differences or a live PDF download.

See the retained [failed attempt](../06_Live_Evaluation/records/post-reranker-2026-09-09/two-job-comparison/) and the [successful rerun](../06_Live_Evaluation/records/post-reranker-2026-09-09/two-job-comparison-rerun-1/).
