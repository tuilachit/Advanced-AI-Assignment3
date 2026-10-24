import type { Interview, Question } from './types'

export const firstQuestion: Question = {
  question_id: 'q1', parent_question_id: null, kind: 'main', category: 'technical',
  status: 'issued', text: 'How did you test your API?', rationale: 'Explore the confirmed project.',
  fact_ids: [], resume_entry_ids: [], job_requirement_excerpt: null,
}

export function interviewFixture(): Interview {
  return {
    schema_version: '1.0', session_id: 's1', interview_id: 'i1', phase: 'active',
    flow_revision: 1, transcript_revision: 0, context_hash: 'fixture-hash',
    profile_revision: 1, resume_entries_revision: 1, cv_id: null, cv_content_hash: null,
    job: { source: 'supplied_job', document_id: 'job1', title: 'Graduate Developer', description: 'APIs' },
    config: { interview_type: 'mixed', duration_minutes: 10, main_question_count: 3,
      max_follow_ups_per_question: 1, language: 'en' },
    questions: [structuredClone(firstQuestion)], current_question_id: 'q1', turns: [],
    feedback_status: 'not_requested', created_at: '2026-10-22T10:00:00Z',
    started_at: '2026-10-22T10:00:00Z', ended_at: null, end_reason: null,
  }
}
