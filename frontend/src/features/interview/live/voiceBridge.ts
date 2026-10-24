import type { ComponentType } from 'react'

import { api } from '../../../api'
import type { Interview } from '../../../types'
import { RealtimeVoiceController } from '../../../voice/controller'
import { interviewApi } from '../../../voice/interviewApi'
import type { VoiceEvent } from '../../../voice/types'

// Derive the UI port from Luke's public API. The scripted preview implements
// this same subset, but is bound only by its separate development entry point.
export type VoiceNotification = VoiceEvent
export type VoiceController = Pick<RealtimeVoiceController,
  'subscribe' | 'connect' | 'set_muted' | 'resume_audio' | 'skip' | 'finish' | 'disconnect'>

export type VisualizerState = 'ready' | 'connecting' | 'listening' | 'speaking' |
  'user-speaking' | 'muted' | 'disconnected' | 'error' | 'finalizing' | 'finished'

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
  // The controller alone owns start/next-step/skip/end, WebRTC and audio cleanup.
  // Construction is inert: microphone access starts only with an explicit connect.
  createController: (sessionId) => new RealtimeVoiceController(interviewApi(sessionId)),
  readInterview: api.getInterview,
}
