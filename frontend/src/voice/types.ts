import type { components } from '../generated/api-schema'

type Schemas = components['schemas']
export type Interview = Schemas['Interview']
export type Question = Schemas['InterviewQuestion']
export type TranscriptTurn = Schemas['TranscriptTurn']
export type NextStep = Schemas['AskQuestionStep'] | Schemas['FinishStep']
export type Credential = Schemas['RealtimeCredential']
export type TurnEvent = Schemas['TurnEventRequest']

export interface InterviewApi {
  get(id: string): Promise<Interview>
  start(id: string, body: Schemas['StartInterviewRequest']): Promise<Schemas['StartInterviewResponse']>
  token(id: string): Promise<Credential>
  turn(id: string, body: TurnEvent): Promise<Schemas['TurnEventAck']>
  next(id: string, body: Schemas['NextStepRequest']): Promise<NextStep>
  skip(id: string, body: Schemas['SkipQuestionRequest']): Promise<NextStep>
  end(id: string, body: Schemas['InterviewControlRequest']): Promise<Interview>
}

export type VoiceEvent =
  | { type: 'connection'; status: 'disconnected' | 'connecting' | 'connected' | 'failed' }
  | { type: 'activity'; candidate_speaking: boolean; interviewer_playing: boolean; muted: boolean }
  | { type: 'transcript'; turn: TranscriptTurn }
  | { type: 'question'; question: Question; flow_revision: number }
  | { type: 'finished'; interview: Interview }
  | { type: 'error'; code: string; message: string; retryable: boolean }

export interface VoiceSessionOptions {
  interview: Interview
  connection_id: string
  api: InterviewApi
  send(event: Record<string, unknown>): void
  emit(event: VoiceEvent): void
  can_hear_audio(): boolean
  retry_delay_ms?: number
}
