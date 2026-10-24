import type { components } from './generated/api-schema'

type ApiSchemas = components['schemas']

export type SessionState = ApiSchemas['SessionState']
export type FactSource = ApiSchemas['FactSource']
export type Fact = ApiSchemas['Fact']
export type FactInput = ApiSchemas['FactInput']
export type FactStatus = ApiSchemas['FactStatus']
export type ProfileDraft = ApiSchemas['ProfileDraft']
export type ProfileUpdateRequest = ApiSchemas['ProfileUpdateRequest']
export type ResumeEntry = ApiSchemas['ResumeEntry']
export type ResumeEntryEdit = ApiSchemas['ResumeEntryEdit']
export type RetrievalResult = ApiSchemas['RetrievalResult']
export type CVClaim = ApiSchemas['CVClaim-Output']
export type CVSection = ApiSchemas['CVSection-Output']
export type CVDocument = ApiSchemas['CVDocument-Output']
export type CVGenerationResponse = ApiSchemas['CVGenerationResponse']
export type ValidationIssue = ApiSchemas['ValidationIssue']
export type TraceEvent = ApiSchemas['TraceEvent']
export type TraceResponse = ApiSchemas['TraceResponse']
export type Session = ApiSchemas['Session']
export type AgentObservation = ApiSchemas['AgentObservation']
export type MessageResponse = ApiSchemas['MessageResponse']
export type ApiErrorBody = ApiSchemas['ApiErrorBody']
export type Interview = ApiSchemas['Interview']
export type CreateInterviewRequest = ApiSchemas['CreateInterviewRequest']
export type InterviewConfig = ApiSchemas['InterviewConfig-Input']
export type InterviewQuestion = ApiSchemas['InterviewQuestion']
export type TranscriptTurn = ApiSchemas['TranscriptTurn']
export type FeedbackRequest = ApiSchemas['FeedbackRequest']
export type FeedbackStartResponse = ApiSchemas['FeedbackStartResponse']
export type FeedbackResponse = ApiSchemas['FeedbackResponse']
export type FeedbackReport = ApiSchemas['FeedbackReport']
export type CriterionFeedback = ApiSchemas['CriterionFeedback']
export type SpeakingMetric = ApiSchemas['SpeakingMetric']

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
}
