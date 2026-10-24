import type { FeedbackReport, FeedbackResponse, Interview } from '../types'
import { preparedInterview } from './interviewFixtures'

// Synthetic HTTP responses for integration/browser tests only. Never imported
// by the application or used to evaluate a user's answers.
export function feedbackFixture() {
  const interview = preparedInterview({ request_id: 'feedback-test', job: { source: 'supplied_job', document_id: 'job-1' },
    consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true } })
  Object.assign(interview, { phase: 'completed', transcript_revision: 7, feedback_status: 'not_requested',
    started_at: '2026-10-24T01:00:00Z', ended_at: '2026-10-24T01:02:00Z', end_reason: 'user_finished' })
  interview.questions[0] = { ...interview.questions[0], category: 'behavioural', status: 'answered', text: 'Tell me about a team project.' }
  interview.questions[1] = { ...interview.questions[1], category: 'technical', status: 'answered', text: 'How would you test an API?' }
  interview.turns = [
    { turn_id: 'answer-0', question_id: 'question-0', speaker: 'candidate', input_mode: 'live_voice',
      transcript_version: 1, transcript_status: 'final', delivery_status: 'not_applicable', timing: null,
      text: 'I built a prototype with my team. We tested two designs.' },
    { turn_id: 'answer-1', question_id: 'question-1', speaker: 'candidate', input_mode: 'live_voice',
      transcript_version: 1, transcript_status: 'final', delivery_status: 'not_applicable', timing: null,
      text: 'I would test the response status and body.' },
  ]
  const report: FeedbackReport = {
    schema_version: '1.0', report_id: 'feedback-test-report', rubric_version: '1.0',
    interview_id: interview.interview_id, context_hash: interview.context_hash, transcript_revision: interview.transcript_revision,
    generated_at: '2026-10-24T01:02:10Z', limitations: ['Only submitted final answers support this evaluation.'],
    question_feedback: [
      { question_id: 'question-0', criteria: [
        { criterion: 'relevance', applicability: 'assessed', score: 3, explanation: 'The answer addresses the team project.',
          evidence: [{ turn_id: 'answer-0', quote: 'I built a prototype with my team.' }], improvement: 'Explain your own responsibility in the team.' },
        { criterion: 'specificity', applicability: 'assessed', score: 0, explanation: 'The designs are not described.',
          evidence: [{ turn_id: 'answer-0', quote: 'We tested two designs.' }], improvement: 'Describe one design and its test outcome.' },
        { criterion: 'structure', applicability: 'assessed', score: 2, explanation: 'Actions are stated but the result is missing.',
          evidence: [{ turn_id: 'answer-0', quote: 'We tested two designs.' }], improvement: null },
        { criterion: 'technical_reasoning', applicability: 'not_applicable', score: null, explanation: 'This question asks about a past experience.', evidence: [], improvement: null },
        { criterion: 'star', applicability: 'assessed', score: 2, explanation: 'Action is visible; the task and result need detail.',
          evidence: [{ turn_id: 'answer-0', quote: 'I built a prototype with my team.' }], improvement: 'Describe the result you actually observed.' },
      ], speaking_metrics: [
        { name: 'words_per_minute', status: 'not_available', value: null, unit: 'words/min', method: 'Uses timed final candidate turns.', unavailable_reason: 'No usable audio timing.', turn_ids: [] },
        { name: 'transcript_filler_count', status: 'available', value: 0, unit: 'count', method: 'Counts preserved filler tokens.', unavailable_reason: null, turn_ids: ['answer-0'] },
        { name: 'pause_count', status: 'not_available', value: null, unit: 'count', method: 'Requires audio analysis.', unavailable_reason: 'No audio-analysis pause intervals.', turn_ids: [] },
      ] },
      { question_id: 'question-1', criteria: [
        { criterion: 'relevance', applicability: 'assessed', score: 3, explanation: 'The answer addresses API testing.', evidence: [{ turn_id: 'answer-1', quote: 'I would test the response status and body.' }], improvement: null },
        { criterion: 'specificity', applicability: 'assessed', score: 1, explanation: 'No example request is described.', evidence: [{ turn_id: 'answer-1', quote: 'the response status and body' }], improvement: null },
        { criterion: 'structure', applicability: 'assessed', score: 2, explanation: 'The approach needs more detail.', evidence: [{ turn_id: 'answer-1', quote: 'the response status and body' }], improvement: null },
        { criterion: 'technical_reasoning', applicability: 'assessed', score: 2, explanation: 'The answer identifies useful assertions.', evidence: [{ turn_id: 'answer-1', quote: 'the response status and body' }], improvement: 'Give an example of an expected response.' },
        { criterion: 'star', applicability: 'not_applicable', score: null, explanation: 'This question asks for an approach.', evidence: [], improvement: null },
      ], speaking_metrics: [
        { name: 'words_per_minute', status: 'not_available', value: null, unit: 'words/min', method: 'Uses timed final candidate turns.', unavailable_reason: 'No usable audio timing.', turn_ids: [] },
        { name: 'transcript_filler_count', status: 'available', value: 0, unit: 'count', method: 'Counts preserved filler tokens.', unavailable_reason: null, turn_ids: ['answer-1'] },
        { name: 'pause_count', status: 'not_available', value: null, unit: 'count', method: 'Requires audio analysis.', unavailable_reason: 'No audio-analysis pause intervals.', turn_ids: [] },
      ] },
    ],
  }
  return { interview, report }
}

export function feedbackResponse(status: FeedbackResponse['feedback_status'], report: FeedbackReport | null = null, retryable = true): FeedbackResponse {
  return { feedback_status: status, report, error: status === 'failed'
    ? { error: { code: 'feedback_provider_unavailable', message: 'Provider detail should not render.', details: { retryable } } } : null }
}

export function unassessedFeedback(interview: Interview): FeedbackReport {
  return { ...feedbackFixture().report, interview_id: interview.interview_id, context_hash: interview.context_hash,
    transcript_revision: interview.transcript_revision, question_feedback: interview.questions.filter((q) => q.status !== 'planned').map((q) => ({
      question_id: q.question_id,
      criteria: (['relevance', 'specificity', 'structure', 'technical_reasoning', 'star'] as const).map((criterion) => ({
        criterion, applicability: 'insufficient_evidence', score: null, explanation: 'No submitted final answer.', evidence: [], improvement: null,
      })), speaking_metrics: feedbackFixture().report.question_feedback[0].speaking_metrics.map((metric) => ({
        ...metric, status: 'not_available', value: null, unavailable_reason: 'No submitted final answer.', turn_ids: [],
      })),
    })) }
}
