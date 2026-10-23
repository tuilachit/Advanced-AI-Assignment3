import { describe, expect, it } from 'vitest'

import { preparedInterview } from '../../../test/interviewFixtures'
import type { Interview, TranscriptTurn } from '../../../types'
import { initialLiveState, liveReducer } from './liveState'

function active(): Interview {
  return { ...preparedInterview({ request_id: 'state-test', job: { source: 'supplied_job', document_id: 'job-1' },
    consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true } }),
  phase: 'active', flow_revision: 2, transcript_revision: 4, current_question_id: 'question-0' }
}
function turn(patch: Partial<TranscriptTurn> = {}): TranscriptTurn {
  return { turn_id: 'turn-1', question_id: 'question-0', speaker: 'candidate', input_mode: 'live_voice',
    transcript_version: 2, transcript_status: 'final', text: 'My saved answer.', delivery_status: 'not_applicable', timing: null, ...patch }
}

describe('voice event and canonical snapshot reconciliation', () => {
  it.each([
    { session_id: 'another-session' }, { interview_id: 'another-interview' },
    { context_hash: 'another-context' }, { flow_revision: 1 }, { transcript_revision: 3 },
  ])('rejects a foreign or older snapshot: %j', (patch) => {
    const state = initialLiveState(active())
    const next = { ...state.interview, ...patch, phase: 'completed' as const }
    expect(liveReducer(state, { type: 'snapshot', interview: next })).toBe(state)
  })

  it('retains final captions and server order while reconciling an active snapshot', () => {
    const final = turn()
    const state = initialLiveState({ ...active(), turns: [final] })
    const earlier = turn({ turn_id: 'earlier', speaker: 'interviewer', text: 'Issued question.' })
    const result = liveReducer(state, { type: 'snapshot', interview: { ...state.interview,
      turns: [earlier, turn({ transcript_version: 3, transcript_status: 'partial', text: 'Late partial' })] } })
    expect(result.interview.turns).toEqual([earlier, final])
  })

  it('uses the completed server snapshot instead of carrying unpersisted live captions into feedback', () => {
    const state = initialLiveState({ ...active(), turns: [turn({ turn_id: 'unconfirmed', transcript_status: 'partial' })] })
    const completed = { ...state.interview, phase: 'completed' as const, flow_revision: 3, turns: [turn()] }
    const result = liveReducer(state, { type: 'finished', interview: completed })
    expect(result.interview).toEqual(completed)
    expect(liveReducer(result, { type: 'transcript', turn: turn({ turn_id: 'late' }) })).toBe(result)
    expect(liveReducer(result, { type: 'activity', muted: false, interviewer_playing: true, candidate_speaking: true })).toBe(result)
  })

  it('does not issue another question while the canonical interview is finalizing', () => {
    const state = initialLiveState({ ...active(), phase: 'finalizing' })
    expect(liveReducer(state, { type: 'question', question: state.interview.questions[1], flow_revision: 3 })).toBe(state)
  })

  it.each(['cancelled', 'failed'] as const)('keeps terminal %s separate from completed', (phase) => {
    const state = initialLiveState(active())
    const result = liveReducer(state, { type: 'finished', interview: { ...state.interview, phase } })
    expect(result.interview.phase).toBe(phase)
    expect(result.connection).toBe('disconnected')
    expect(result.activity.muted).toBe(true)
  })
})
