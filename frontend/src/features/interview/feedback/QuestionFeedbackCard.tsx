import type { Interview, InterviewQuestion } from '../../../types'
import { CriteriaFeedback } from './CriteriaFeedback'
import { SpeakingMetrics } from './SpeakingMetrics'
import type { QuestionReview } from './feedbackView'

export function questionLabel(question: InterviewQuestion, interview: Interview) {
  const mains = interview.questions.filter((item) => item.kind === 'main')
  const parent = question.kind === 'follow_up' ? question.parent_question_id : question.question_id
  const index = mains.findIndex((item) => item.question_id === parent)
  return `Question ${index < 0 ? '—' : index + 1}${question.kind === 'follow_up' ? ' · Follow-up' : ''}`
}

export function QuestionFeedbackCard({ question, review, interview, initiallyOpen, onEvidence }: {
  question: InterviewQuestion; review?: QuestionReview; interview: Interview; initiallyOpen: boolean; onEvidence: (turnId: string) => void
}) {
  const status = question.status === 'answered' ? 'Answered' : question.status === 'skipped' ? 'Skipped' : 'No submitted answer'
  return <details className="feedback-question" open={initiallyOpen}>
    <summary><div className="feedback-question-top"><span className="feedback-question-number">{questionLabel(question, interview)}</span>
      <span className="feedback-question-category">{question.category}</span><span className="feedback-answer-status">{status}</span></div>
      <h3>{question.text}</h3><span className="feedback-expand-label">Review answer <span aria-hidden="true">↓</span></span></summary>
    <div className="feedback-question-body">
      {review?.criteria.length ? <CriteriaFeedback criteria={review.criteria} questionId={question.question_id} interview={interview} onEvidence={onEvidence} />
        : <p className="interview-notice">Criterion feedback is not available for this question.</p>}
      {review?.measures.length ? <SpeakingMetrics measures={review.measures} /> : <p className="feedback-help">Speaking metrics are not available for this question.</p>}
    </div>
  </details>
}
