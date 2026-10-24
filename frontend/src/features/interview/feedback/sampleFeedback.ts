import type { Interview, InterviewQuestion, TranscriptTurn } from '../../../types'
import { criterionLabels, type CriterionKey, type CriterionReview, type FeedbackSource, type FeedbackView,
  type QuestionReview, type SpeakingMeasure } from './feedbackView'

// Explicitly fictional UI sample. Never derived from, attached to, or saved over
// a user's interview. Numbers below are fixtures, not a client-side assessment.
const answerOne = 'In our course-planning project, um, I compared two API designs. I built a small prototype and reviewed the trade-offs with my team. We chose the simpler design because it was easier to test.'
const answerFollowUp = 'I learned to test a small version of an idea before committing the team to it. Next time I would agree on the test cases earlier.'
const answerTwo = 'I would test valid requests, missing fields and invalid identifiers. I would separate unit tests for validation from integration tests against a test database. I would also check the response status and body for each case.'

function question(id: string, text: string, category: InterviewQuestion['category'], status: InterviewQuestion['status'], parent: string | null = null): InterviewQuestion {
  return { question_id: id, text, category, status, kind: parent ? 'follow_up' : 'main', parent_question_id: parent,
    rationale: 'Synthetic UI review question.', fact_ids: [], resume_entry_ids: [], job_requirement_excerpt: null }
}
function answer(id: string, questionId: string, text: string, timed = false): TranscriptTurn {
  return { turn_id: id, question_id: questionId, speaker: 'candidate', input_mode: 'live_voice',
    transcript_version: 1, transcript_status: 'final', text, delivery_status: 'not_applicable',
    timing: timed ? { clock_id: 'sample-audio', start_ms: 0, end_ms: 20_000, source: 'provider_vad' } : null }
}
function assessed(key: CriterionKey, score: 0 | 1 | 2 | 3 | 4, explanation: string, turnId: string, excerpt: string, suggestion?: string): CriterionReview {
  return { key, rating: { kind: 'assessed', score }, explanation, evidence: [{ turnId, excerpt }], suggestion }
}
function notApplicable(key: CriterionKey, explanation: string): CriterionReview {
  return { key, rating: { kind: 'notApplicable' }, explanation, evidence: [] }
}
function measures(turnId?: string, timed = false, fillers = 0): SpeakingMeasure[] {
  return [
    { key: 'pace', measurement: timed ? { kind: 'available', value: 105, unit: 'words/min' }
      : { kind: 'unavailable', reason: 'No valid positive audio timing is available for this answer.' },
      method: 'Approximate transcript words per minute, using only timed final candidate turns. Overlapping intervals are merged within the same audio clock. Untimed words are excluded. This is not articulation speed.', turnIds: timed && turnId ? [turnId] : [] },
    { key: 'fillers', measurement: turnId ? { kind: 'available', value: fillers, unit: 'count' }
      : { kind: 'unavailable', reason: 'There is no usable final candidate transcript for this question.' },
      method: 'Counts exact um, uh, erm and er tokens preserved in final candidate transcripts. Speech recognition can omit or alter fillers; this does not count every filler spoken.', turnIds: turnId ? [turnId] : [] },
    { key: 'pauses', measurement: { kind: 'unavailable', reason: 'Audio-analysis pause intervals and a documented threshold were not supplied.' },
      method: 'Pauses are not inferred from punctuation, transcript arrival times or ordinary gaps.', turnIds: [] },
  ]
}
function missingReview(questionId: string): QuestionReview {
  return { questionId, criteria: (Object.keys(criterionLabels) as CriterionKey[]).map((key) => ({
    key, rating: { kind: 'insufficientEvidence' }, explanation: 'No submitted final answer is available to assess this criterion.', evidence: [],
    suggestion: key === 'relevance' ? 'Practise answering this question aloud, using an example you can support from your experience.' : undefined,
  })), measures: measures() }
}

export type SampleScenario = 'ready' | 'retry' | 'loading' | 'insufficient' | 'empty'

export function createSampleFeedback(scenario: SampleScenario = 'ready'): { interview: Interview; report: FeedbackView; source: FeedbackSource } {
  const interview: Interview = {
    schema_version: '1.0', session_id: 'sample-feedback-session', interview_id: 'sample-feedback-interview',
    phase: 'completed', flow_revision: 7, transcript_revision: 3, context_hash: 'synthetic-feedback-context',
    profile_revision: 1, resume_entries_revision: 1, cv_id: null, cv_content_hash: null,
    job: { source: 'pasted_job', document_id: null, title: 'Graduate Software Engineer', description: 'Build and test software with a collaborative team.' },
    config: { interview_type: 'mixed', duration_minutes: 10, main_question_count: 4, max_follow_ups_per_question: 1, language: 'en' },
    questions: [
      question('sample-q1', 'Tell me about a project where you had to make a difficult technical decision.', 'behavioural', 'answered'),
      question('sample-q1-follow-up', 'What did you learn, and what would you change next time?', 'behavioural', 'answered', 'sample-q1'),
      question('sample-q2', 'How would you test an API before releasing it to users?', 'technical', 'answered'),
      question('sample-q3', 'Tell me about a time you helped your team resolve a disagreement.', 'behavioural', 'skipped'),
      question('sample-q4', 'How would you investigate a slow API response?', 'technical', 'planned'),
    ],
    turns: [answer('sample-turn-1', 'sample-q1', answerOne, true), answer('sample-turn-2', 'sample-q1-follow-up', answerFollowUp),
      answer('sample-turn-3', 'sample-q2', answerTwo)],
    current_question_id: 'sample-q3', feedback_status: 'ready', created_at: '2026-10-23T02:00:00Z',
    started_at: '2026-10-23T02:01:00Z', ended_at: '2026-10-23T02:07:20Z', end_reason: 'user_finished',
  }
  const report: FeedbackView = {
    interviewId: interview.interview_id, contextHash: interview.context_hash, transcriptRevision: interview.transcript_revision,
    rubricVersion: '1.0', createdAt: '2026-10-23T02:07:30Z',
    questions: [
      { questionId: 'sample-q1', criteria: [
        assessed('relevance', 3, 'The answer stays on the design decision and connects it to your project.', 'sample-turn-1', 'I compared two API designs.'),
        assessed('specificity', 2, 'The prototype is a concrete action, but the alternatives and test results are not described.', 'sample-turn-1', 'I built a small prototype',
          'Name the two alternatives and explain one concrete difference you tested. Use details you actually remember.'),
        assessed('structure', 3, 'The answer moves from project context to your actions and the team’s choice.', 'sample-turn-1', 'We chose the simpler design because it was easier to test.'),
        notApplicable('technicalReasoning', 'This behavioural question assesses your experience and decision process. Technical reasoning is not separately scored here.'),
        assessed('star', 2, 'Situation and action are visible. Your responsibility and the observed result need more detail.', 'sample-turn-1', 'In our course-planning project, um, I compared two API designs.',
          'State your responsibility, then describe the result you observed. If you did not measure an outcome, explain the qualitative result without inventing a number.'),
      ], measures: measures('sample-turn-1', true, 1) },
      { questionId: 'sample-q1-follow-up', criteria: [
        assessed('relevance', 3, 'The answer identifies a lesson and a change for next time.', 'sample-turn-2', 'Next time I would agree on the test cases earlier.'),
        assessed('specificity', 2, 'Earlier agreement is concrete; the answer could explain who would be involved.', 'sample-turn-2', 'agree on the test cases earlier',
          'Explain who you would involve and when you would agree on the test cases.'),
        assessed('structure', 3, 'The lesson and next action are easy to follow.', 'sample-turn-2', 'I learned to test a small version of an idea before committing the team to it.'),
        notApplicable('technicalReasoning', 'This follow-up asks about learning from a past experience, rather than assessing a technical solution.'),
        assessed('star', 2, 'The reflection is clear, but the impact of the change is not yet explained.', 'sample-turn-2', 'Next time I would agree on the test cases earlier.',
          'Connect the lesson to the outcome of your earlier decision, using only what happened.'),
      ], measures: measures('sample-turn-2') },
      { questionId: 'sample-q2', criteria: [
        assessed('relevance', 3, 'The answer directly addresses API testing before release.', 'sample-turn-3', 'I would test valid requests, missing fields and invalid identifiers.'),
        assessed('specificity', 2, 'You name test categories, but do not provide a concrete request and expected response.', 'sample-turn-3', 'I would also check the response status and body for each case.',
          'Give one example request, its expected status and response body, and the failure it would catch.'),
        assessed('structure', 3, 'The response separates test cases, test levels and assertions.', 'sample-turn-3', 'I would separate unit tests for validation from integration tests against a test database.'),
        assessed('technicalReasoning', 3, 'The distinction between isolated validation and database integration is relevant to the proposed approach.', 'sample-turn-3', 'unit tests for validation from integration tests against a test database',
          'Explain why both test levels are needed and how you would keep test data repeatable.'),
        notApplicable('star', 'This technical question asks for an approach, rather than a past-experience story.'),
      ], measures: measures('sample-turn-3') },
      missingReview('sample-q3'),
    ],
    limitations: [
      'This sample uses synthetic answers and illustrative coaching. It is not an evaluation of your conversation.',
      'Only final submitted candidate answers support criterion feedback. Missing answers are not given a zero.',
      'Speaking metrics describe the available transcript and timing evidence. They do not assess accent, personality or emotion.',
      'Transcript quotes do not verify the truth of real-world claims. Interview statements do not become confirmed CV facts.',
    ],
  }
  if (scenario === 'insufficient') {
    interview.turns = [answer('sample-failed-turn', 'sample-q1', '')]
    interview.turns[0].transcript_status = 'failed'
    interview.questions = interview.questions.filter((item) => item.kind === 'main')
      .map((item) => ({ ...item, status: item.question_id === 'sample-q1' ? 'issued' : 'planned' }))
    interview.current_question_id = 'sample-q1'
    report.questions = [missingReview('sample-q1')]
  }
  if (scenario === 'empty') {
    interview.questions = interview.questions.filter((item) => item.kind === 'main').map((item) => ({ ...item, status: 'planned' }))
    interview.turns = []
    interview.current_question_id = null
    report.questions = []
  }
  let attempts = 0
  const source: FeedbackSource = { kind: 'sample', load: (_interview, signal) => new Promise((resolve, reject) => {
    attempts++
    const failThisAttempt = scenario === 'retry' && attempts === 1
    const aborted = () => { clearTimeout(timer); reject(new DOMException('Sample load cancelled', 'AbortError')) }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', aborted)
      if (failThisAttempt) reject(new Error('Simulated sample loading failure'))
      else resolve(structuredClone(report))
    }, scenario === 'loading' ? 3_600_000 : 650)
    signal.addEventListener('abort', aborted, { once: true })
    if (signal.aborted) aborted()
  }) }
  return { interview, report, source }
}
