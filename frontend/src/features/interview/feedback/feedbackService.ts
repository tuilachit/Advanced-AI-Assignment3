import { api } from '../../../api'
import type { CriterionFeedback, FeedbackReport, SpeakingMetric } from '../../../types'
import type { CriterionReview, FeedbackView, ServiceFeedbackSource, SpeakingMeasure } from './feedbackView'

function criterionView(item: CriterionFeedback): CriterionReview {
  let rating: CriterionReview['rating']
  if (item.applicability === 'assessed') {
    // OpenAPI represents this constrained integer as number. Reject malformed
    // assessed scores rather than silently substituting zero or missing evidence.
    const score = item.score
    if (score !== 0 && score !== 1 && score !== 2 && score !== 3 && score !== 4) throw new Error('Invalid criterion score')
    rating = { kind: 'assessed', score }
  } else rating = { kind: item.applicability === 'not_applicable' ? 'notApplicable' : 'insufficientEvidence' }
  return { key: item.criterion === 'technical_reasoning' ? 'technicalReasoning' : item.criterion,
    rating, explanation: item.explanation, evidence: item.evidence.map((quote) => ({ turnId: quote.turn_id, excerpt: quote.quote })),
    suggestion: item.improvement ?? undefined }
}

function measureView(item: SpeakingMetric): SpeakingMeasure {
  let measurement: SpeakingMeasure['measurement']
  if (item.status === 'available') {
    if (item.value === null || !Number.isFinite(item.value) || item.value < 0) throw new Error('Invalid speaking measurement')
    measurement = { kind: 'available', value: item.value, unit: item.unit }
  } else measurement = { kind: 'unavailable', reason: item.unavailable_reason ?? 'No measurement is available for this answer.' }
  return { key: item.name === 'words_per_minute' ? 'pace' : item.name === 'transcript_filler_count' ? 'fillers' : 'pauses',
    measurement, method: item.method, turnIds: item.turn_ids }
}

export function feedbackView(report: FeedbackReport): FeedbackView {
  return { interviewId: report.interview_id, contextHash: report.context_hash, transcriptRevision: report.transcript_revision,
    rubricVersion: report.rubric_version, createdAt: report.generated_at, limitations: report.limitations,
    questions: report.question_feedback.map((question) => ({ questionId: question.question_id,
      criteria: question.criteria.map(criterionView), measures: question.speaking_metrics.map(measureView) })) }
}

export const feedbackService: ServiceFeedbackSource = {
  kind: 'service',
  async read(interview, signal) {
    const response = await api.getFeedback(interview.session_id, interview.interview_id, signal)
    switch (response.feedback_status) {
      case 'ready':
        if (!response.report) throw new Error('Missing feedback report')
        return { status: 'ready', report: feedbackView(response.report) }
      case 'failed':
        return { status: 'failed', retryable: response.error?.error.details.retryable === true,
          message: response.error?.error.details.retryable === true
            ? 'Feedback generation failed. Your completed interview is kept. You can try generating feedback again.'
            : 'Feedback generation failed. Return to the interview to check its latest state before trying again.' }
      case 'not_requested': return { status: 'not_requested' }
      case 'generating': return { status: 'generating' }
      default: throw new Error('Unknown feedback status')
    }
  },
  async generate(interview, requestId, signal) {
    // Send the revision, never the browser transcript. The backend selects the
    // canonical final submitted answers and owns all evaluation/deduplication.
    await api.generateFeedback(interview.session_id, interview.interview_id,
      { request_id: requestId, expected_transcript_revision: interview.transcript_revision }, signal)
  },
}
