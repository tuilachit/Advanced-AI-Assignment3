import type { Interview } from '../../../types'

// Presentation models, not wire DTOs. Sunny's feedback models are not in the
// merged OpenAPI schema yet. A future adapter maps generated API aliases here.
export type CriterionKey = 'relevance' | 'specificity' | 'structure' | 'technicalReasoning' | 'star'
export interface EvidenceReference { turnId: string; excerpt: string }
export interface CriterionReview {
  key: CriterionKey
  rating: { kind: 'assessed'; score: 0 | 1 | 2 | 3 | 4 } |
    { kind: 'notApplicable' | 'insufficientEvidence' }
  explanation: string
  evidence: EvidenceReference[]
  suggestion?: string
}
export interface SpeakingMeasure {
  key: 'pace' | 'fillers' | 'pauses'
  measurement: { kind: 'available'; value: number; unit: 'words/min' | 'count' } |
    { kind: 'unavailable'; reason: string }
  method: string
  turnIds: string[]
}
export interface QuestionReview {
  questionId: string
  criteria: CriterionReview[]
  measures: SpeakingMeasure[]
}
export interface FeedbackView {
  interviewId: string
  contextHash: string
  transcriptRevision: number
  rubricVersion: string
  createdAt: string
  questions: QuestionReview[]
  limitations: string[]
}

export interface FeedbackSource {
  kind: 'sample' | 'service'
  // The future adapter owns API request IDs, start/poll behaviour and conversion
  // from generated types. The screen does not guess routes or implement scoring.
  load(interview: Interview, signal: AbortSignal): Promise<FeedbackView>
}

export const criterionLabels: Record<CriterionKey, string> = {
  relevance: 'Relevance', specificity: 'Specificity', structure: 'Structure',
  technicalReasoning: 'Technical reasoning', star: 'STAR',
}
export const scoreAnchors = [
  'Does not address the criterion', 'Limited', 'Partially meets the criterion',
  'Clear and well supported', 'Specific, well reasoned and strongly supported',
] as const

export function reportMatchesInterview(report: FeedbackView, interview: Interview) {
  return report.interviewId === interview.interview_id && report.contextHash === interview.context_hash &&
    report.transcriptRevision === interview.transcript_revision
}

export function evidenceTurn(interview: Interview, questionId: string, reference: EvidenceReference) {
  return interview.turns.find((turn) => turn.turn_id === reference.turnId && turn.question_id === questionId &&
    turn.speaker === 'candidate' && turn.transcript_status === 'final' &&
    reference.excerpt.trim() && turn.text.includes(reference.excerpt))
}
