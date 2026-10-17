import type { CVClaim, CVDocument, Fact } from '../types'

export interface ReviewedSampleCV {
  filename: string
  profileDocumentId: string
  targetJobTitle: string
  facts: Fact[]
  cv: CVDocument
}

function fact(profileId: string, id: string, field: string, value: string): Fact {
  return {
    fact_id: id,
    field,
    value,
    status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: profileId },
  }
}

function claim(id: string, text: string, factIds: string[]): CVClaim {
  return { claim_id: id, text, fact_ids: factIds, verified: true }
}

const mayaFacts = [
  fact('student_profile_01', 'maya-name', 'name', 'Maya Chen'),
  fact(
    'student_profile_01',
    'maya-study',
    'education',
    'Third-year Bachelor of Computing Science student at the University of Technology Sydney.',
  ),
  fact(
    'student_profile_01',
    'maya-course-planner',
    'project',
    'Contributed Python service logic, SQL queries, REST endpoints, input validation and unit tests to a team course-planning API.',
  ),
  fact(
    'student_profile_01',
    'maya-agent',
    'project',
    'Created a coursework tool-call agent prototype that selected local tools and recorded tool results before responding.',
  ),
  fact(
    'student_profile_01',
    'maya-skills',
    'skills',
    'Python, Java, SQL, REST APIs, Git, GitHub, pytest and Jupyter Notebook.',
  ),
  fact(
    'student_profile_01',
    'maya-retail',
    'experience',
    'Worked with a small retail team, answered customer questions and followed written procedures during busy periods.',
  ),
]

const liamFacts = [
  fact('student_profile_02', 'liam-name', 'name', 'Liam Patel'),
  fact(
    'student_profile_02',
    'liam-study',
    'education',
    'Bachelor of Computing Science student at the University of Technology Sydney focused on NLP and practical LLM applications.',
  ),
  fact(
    'student_profile_02',
    'liam-retrieval',
    'project',
    'Built a retrieval-augmented coursework assistant over local job descriptions, compared prompts and documented uncertain outputs.',
  ),
  fact(
    'student_profile_02',
    'liam-classifier',
    'project',
    'Prepared a labelled text dataset, trained a baseline classifier and compared precision and recall across two model settings.',
  ),
  fact(
    'student_profile_02',
    'liam-skills',
    'skills',
    'Python, pandas, NumPy, scikit-learn, PyTorch basics, SQL, Hugging Face Transformers basics, Git and Jupyter Notebook.',
  ),
]

export const sampleCVs: ReviewedSampleCV[] = [
  {
    filename: 'sample-01-maya-chen-graduate-ai.pdf',
    profileDocumentId: 'student_profile_01',
    targetJobTitle: 'Graduate AI Engineer',
    facts: mayaFacts,
    cv: {
      cv_id: 'sample-cv-01',
      target_job_id: 'graduate_ai_engineer',
      headline: 'Computing Science student | Python, APIs and applied AI',
      headline_fact_ids: ['maya-study', 'maya-skills', 'maya-agent'],
      claims: [
        claim('maya-profile', 'Third-year Computing Science student with project evidence in Python APIs and applied AI.', ['maya-study', 'maya-course-planner', 'maya-agent']),
      ],
      sections: [
        {
          heading: 'Selected projects',
          claims: [
            claim('maya-project-1', 'Contributed Python service logic, SQL queries, REST endpoint design, validation and unit tests to a team course-planning API.', ['maya-course-planner']),
            claim('maya-project-2', 'Created a tool-call agent prototype that selected local course tools and recorded each tool result before responding.', ['maya-agent']),
          ],
        },
        {
          heading: 'Technical skills',
          claims: [claim('maya-skills-1', 'Python, Java, SQL, REST APIs, Git, GitHub, pytest and Jupyter Notebook.', ['maya-skills'])],
        },
        {
          heading: 'Experience',
          claims: [claim('maya-experience-1', 'Answered customer questions, collaborated with a small retail team and followed written procedures during busy periods.', ['maya-retail'])],
        },
      ],
    },
  },
  {
    filename: 'sample-02-maya-chen-agentic-ai.pdf',
    profileDocumentId: 'student_profile_01',
    targetJobTitle: 'AI Engineer - agentic workflows',
    facts: mayaFacts,
    cv: {
      cv_id: 'sample-cv-02',
      target_job_id: 'agentic_ai_engineer',
      headline: 'Computing Science student | Python workflows and testing',
      headline_fact_ids: ['maya-study', 'maya-course-planner', 'maya-agent'],
      claims: [
        claim('maya-agentic-profile', 'Computing Science student with evidence in Python service development, tool-call workflows and team delivery.', ['maya-study', 'maya-course-planner', 'maya-agent']),
      ],
      sections: [
        {
          heading: 'Technical skills',
          claims: [
            claim('maya-agentic-skills', 'Python, Java, SQL, REST APIs, Git, GitHub, pytest and Jupyter Notebook.', ['maya-skills']),
          ],
        },
        {
          heading: 'Selected AI and software work',
          claims: [
            claim('maya-agentic-project-1', 'Created a bounded tool-call agent prototype that selected local tools and recorded results before responding.', ['maya-agent']),
            claim('maya-agentic-project-2', 'Contributed service logic, endpoint design, input validation and automated tests to a team course-planning API.', ['maya-course-planner']),
          ],
        },
        {
          heading: 'Team and customer experience',
          claims: [
            claim('maya-agentic-experience', 'Collaborated with a small retail team, answered customer questions and followed written procedures during busy periods.', ['maya-retail']),
          ],
        },
      ],
    },
  },
  {
    filename: 'sample-03-liam-patel-rag-ai.pdf',
    profileDocumentId: 'student_profile_02',
    targetJobTitle: 'AI Engineer - RAG and agents',
    facts: liamFacts,
    cv: {
      cv_id: 'sample-cv-03',
      target_job_id: 'rag_agent_engineer',
      headline: 'Computing Science student | Retrieval, NLP and model evaluation',
      headline_fact_ids: ['liam-study', 'liam-retrieval', 'liam-classifier'],
      claims: [
        claim('liam-profile', 'Computing Science student focused on NLP, retrieval and practical LLM applications.', ['liam-study', 'liam-retrieval']),
      ],
      sections: [
        {
          heading: 'Selected projects',
          claims: [
            claim('liam-project-1', 'Built a retrieval-augmented assistant over local job descriptions, compared prompts, inspected evidence and documented uncertainty.', ['liam-retrieval']),
            claim('liam-project-2', 'Prepared a labelled text dataset, trained a baseline classifier and compared precision and recall across two settings.', ['liam-classifier']),
          ],
        },
        {
          heading: 'Technical skills',
          claims: [claim('liam-skills-1', 'Python, pandas, NumPy, scikit-learn, PyTorch basics, SQL, Hugging Face Transformers basics, Git and Jupyter Notebook.', ['liam-skills'])],
        },
      ],
    },
  },
]
