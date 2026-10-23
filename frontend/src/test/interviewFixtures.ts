import type { CreateInterviewRequest, Interview, Session } from '../types'

// Synthetic test and standalone development-preview data; not used by the main application.
export function interviewSession(): Session {
  return {
    session_id: 'setup-test-session', state: 'cv_validated',
    profile: { revision: 1, facts: [
      { fact_id: 'project-fact', field: 'project', value: 'Built a Python course-planning API.',
        status: 'confirmed', source: { source_type: 'user_message', reference: 'test-introduction' } },
    ] },
    resume_entries: [{
      entry_id: 'approved-project', kind: 'project', status: 'approved',
      heading: { text: 'Course-planning API', fact_ids: ['project-fact'] },
      organisation_or_context: null, details: [], bullets: [],
      source_fact_ids: ['project-fact'],
    }],
    resume_entries_revision: 1, resume_entry_validation_issues: [],
    retrieval_results: ['Graduate AI Engineer', 'Graduate Software Engineer'].map((title, index) => ({
      document_id: 'job-' + index, title, score: 0.8,
      score_breakdown: { semantic_score: 0.8, project_score: 0.8, skill_score: 0.8,
        target_role_score: 0.8, education_score: 0.8, experience_score: 0.8, evidence_score: 0.8, final_score: 0.8 },
      excerpt: 'Build and test Python APIs.', match_reasons: ['Confirmed Python project.'],
      matched_skills: ['Python'], missing_requirements: [], eligibility_notes: ['Review the full role.'],
    })),
    selected_job_id: 'job-1',
    cv: { cv_id: 'validated-cv', target_job_id: 'job-1', headline: 'Python project experience',
      headline_fact_ids: ['project-fact'],
      claims: [{ claim_id: 'project-claim', text: 'Built a Python course-planning API.',
        fact_ids: ['project-fact'], verified: true }], sections: [] },
    validation_issues: [], validated_content_hash: 'test-cv-hash', trace: [],
  }
}

export function preparedInterview(body: CreateInterviewRequest, session = interviewSession()): Interview {
  const config = body.config ?? {
    interview_type: 'mixed', duration_minutes: 10, main_question_count: 4,
    max_follow_ups_per_question: 1, language: 'en',
  }
  return {
    schema_version: '1.0', session_id: session.session_id, interview_id: 'prepared-interview',
    phase: 'ready', flow_revision: 0, transcript_revision: 0, context_hash: 'test-context-hash',
    profile_revision: session.profile.revision, resume_entries_revision: session.resume_entries_revision,
    cv_id: body.cv_id ?? null, cv_content_hash: body.cv_id ? session.validated_content_hash : null,
    job: body.job.source === 'pasted_job' ? { ...body.job, document_id: null } : {
      source: 'supplied_job', document_id: body.job.document_id,
      title: session.retrieval_results.find((job) => job.document_id === ('document_id' in body.job ? body.job.document_id : ''))?.title ?? 'Test job',
      description: 'Build and test Python APIs.',
    },
    config,
    questions: Array.from({ length: config.main_question_count }, (_, index) => ({
      question_id: 'question-' + index, parent_question_id: null, kind: 'main',
      category: config.interview_type === 'technical' ? 'technical' : 'behavioural', status: 'planned',
      text: 'Tell me about a project decision ' + (index + 1) + '.',
      rationale: 'Practise explaining confirmed experience.', fact_ids: ['project-fact'],
      resume_entry_ids: ['approved-project'], job_requirement_excerpt: null,
    })),
    current_question_id: null, turns: [], feedback_status: 'not_requested',
    created_at: '2026-10-23T00:00:00Z', started_at: null, ended_at: null, end_reason: null,
  }
}
