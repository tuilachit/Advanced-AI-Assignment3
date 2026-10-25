import type { Interview, TranscriptTurn } from '../../../types'
import type { VisualizerState, VoiceNotification } from './voiceBridge'

export type VoiceProblem = Extract<VoiceNotification, { type: 'error' }>
export interface LiveState {
  interview: Interview
  connection: Extract<VoiceNotification, { type: 'connection' }>['status']
  activity: Omit<Extract<VoiceNotification, { type: 'activity' }>, 'type'>
  error: VoiceProblem | null
}

export const isTerminal = (interview: Interview) => ['completed', 'cancelled', 'failed'].includes(interview.phase)
const silent = { muted: true, candidate_speaking: false, interviewer_playing: false }
export const initialLiveState = (interview: Interview): LiveState => ({ interview, connection: 'disconnected', activity: silent, error: null })

export function canApplySnapshot(current: Interview, next: Interview): boolean {
  return next.session_id === current.session_id && next.interview_id === current.interview_id &&
    next.context_hash === current.context_hash && next.flow_revision >= current.flow_revision &&
    next.transcript_revision >= current.transcript_revision &&
    (!isTerminal(current) || next.phase === current.phase)
}

// Display reconciliation only. The controller persists turns; the backend decides
// question order. Never replace final captions with late partial/stale events.
export function mergeTurns(current: TranscriptTurn[], incoming: TranscriptTurn[]): TranscriptTurn[] {
  const result = new Map(current.map((turn) => [turn.turn_id, turn]))
  for (const turn of incoming) {
    const previous = result.get(turn.turn_id)
    if (previous && (turn.transcript_version <= previous.transcript_version ||
      (previous.transcript_status === 'final' && turn.transcript_status !== 'final'))) continue
    result.set(turn.turn_id, turn)
  }
  return [...result.values()]
}

export type LiveAction = VoiceNotification | { type: 'snapshot'; interview: Interview } |
  { type: 'clear-error' } | { type: 'command-error'; message: string }

export function liveReducer(state: LiveState, event: LiveAction): LiveState {
  switch (event.type) {
    case 'snapshot':
    case 'finished': {
      const next = event.interview
      if (!canApplySnapshot(state.interview, next)) return state
      // Active captions can lead a GET response. Reconcile without downgrading
      // finals, retaining canonical order. A terminal snapshot is authoritative:
      // unsaved live captions must not become part of the feedback context.
      const ordered = new Map(next.turns.map((turn) => [turn.turn_id, turn]))
      if (!isTerminal(next)) {
        for (const turn of mergeTurns(state.interview.turns, next.turns)) ordered.set(turn.turn_id, turn)
      }
      return { ...state, interview: { ...next, turns: [...ordered.values()] },
        error: state.error?.code === 'api_unreachable' ? null : state.error,
        ...(isTerminal(next) ? { connection: 'disconnected', activity: silent, error: null } : {}) }
    }
    case 'connection':
      return { ...state, connection: isTerminal(state.interview) ? 'disconnected' : event.status,
        activity: event.status === 'connected' ? { ...silent, muted: false } : silent }
    case 'activity':
      return state.connection === 'connected' && !isTerminal(state.interview)
        ? { ...state, activity: event } : state
    case 'question': {
      if (isTerminal(state.interview) || state.interview.phase === 'finalizing' ||
        event.flow_revision < state.interview.flow_revision) return state
      const questions = state.interview.questions.filter((question) => question.question_id !== event.question.question_id)
      // Keep the original plan order when replacing an issued main question.
      const existing = state.interview.questions.some((question) => question.question_id === event.question.question_id)
      return { ...state, interview: { ...state.interview, current_question_id: event.question.question_id,
        flow_revision: event.flow_revision,
        questions: existing ? state.interview.questions.map((question) => question.question_id === event.question.question_id ? event.question : question)
          : [...questions, event.question] } }
    }
    case 'transcript':
      return isTerminal(state.interview) ? state
        : { ...state, interview: { ...state.interview, turns: mergeTurns(state.interview.turns, [event.turn]) } }
    case 'error': return isTerminal(state.interview) ? state : { ...state, error: event }
    case 'clear-error': return { ...state, error: null }
    case 'command-error': return isTerminal(state.interview) ? state : { ...state, error: state.error ?? {
      type: 'error', code: 'control_failed', message: event.message, retryable: true,
    } }
  }
}

export function visualizerState(state: LiveState): VisualizerState {
  if (state.interview.phase === 'failed') return 'error'
  if (isTerminal(state.interview)) return 'finished'
  if (state.interview.phase === 'finalizing') return 'finalizing'
  if (state.connection === 'connecting') return 'connecting'
  if (state.error || state.connection === 'failed') return 'error'
  if (state.connection !== 'connected') return state.interview.phase === 'ready' ? 'ready' : 'disconnected'
  if (state.activity.muted) return 'muted'
  if (state.activity.candidate_speaking) return 'user-speaking'
  if (state.activity.interviewer_playing) return 'speaking'
  return 'listening'
}

export function remainingSeconds(interview: Interview, now: number): number {
  const duration = interview.config.duration_minutes * 60
  if (!interview.started_at) return duration
  const started = Date.parse(interview.started_at)
  const end = interview.ended_at ? Date.parse(interview.ended_at) : now
  return Number.isFinite(started) && Number.isFinite(end)
    ? Math.max(0, Math.min(duration, Math.ceil(duration - (end - started) / 1000))) : duration
}
