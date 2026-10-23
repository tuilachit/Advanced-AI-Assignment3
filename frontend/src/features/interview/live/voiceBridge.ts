import type { ComponentType } from 'react'

import { api } from '../../../api'
import type { Interview, InterviewQuestion, TranscriptTurn } from '../../../types'

// UI boundary matching Luke's controller at 022a352. These are local controller
// notifications, not a second API schema. All wire records use generated aliases.
export type VoiceNotification =
  | { type: 'connection'; status: 'disconnected' | 'connecting' | 'connected' | 'failed' }
  | { type: 'activity'; candidate_speaking: boolean; interviewer_playing: boolean; muted: boolean }
  | { type: 'transcript'; turn: TranscriptTurn }
  | { type: 'question'; question: InterviewQuestion; flow_revision: number }
  | { type: 'finished'; interview: Interview }
  | { type: 'error'; code: string; message: string; retryable: boolean }

export interface VoiceController {
  subscribe(listener: (event: VoiceNotification) => void): () => void
  connect(interviewId: string): Promise<void>
  set_muted(muted: boolean): void
  resume_audio(): Promise<void>
  skip(): Promise<void>
  finish(): Promise<Interview>
  disconnect(): void
}

// Keep this small port until PR #2 is integrated, then derive it from Luke's
// VoiceEvent / public controller methods. No dynamic imports, alternate voice
// implementation or simulated fallback belongs in the application's binding.

export type VisualizerState = 'ready' | 'connecting' | 'listening' | 'speaking' |
  'user-speaking' | 'muted' | 'error' | 'finalizing' | 'finished'

export interface VisualizerProps {
  state: VisualizerState
  interview: Interview
  controller: VoiceController | null
}

export interface VoiceIntegration {
  createController(sessionId: string): VoiceController | null
  readInterview(sessionId: string, interviewId: string): Promise<Interview>
  Visualizer?: ComponentType<VisualizerProps>
}

export const voiceIntegration: VoiceIntegration = {
  // Single binding point once Luke's modules are available on this branch:
  // (sessionId) => new RealtimeVoiceController(interviewApi(sessionId))
  // The controller alone owns start/next-step/skip/end, WebRTC and audio cleanup.
  createController: () => null,
  readInterview: api.getInterview,
}
