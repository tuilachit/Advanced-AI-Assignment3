import { expect, it } from 'vitest'

import { VoiceOrbView } from './orbView'
import { interviewFixture } from './testFixtures'

function setup() {
  const orb = document.createElement('div')
  const label = document.createElement('p')
  const hint = document.createElement('p')
  const view = new VoiceOrbView(orb, label, hint)
  return { orb, label, hint, view }
}

it('does not display listening before a connection is established', () => {
  const { view, orb, label } = setup()
  expect(orb.dataset.state).toBe('idle')
  view.ready()
  expect(orb.dataset.state).toBe('ready')
  view.handle({ type: 'connection', status: 'connecting' })
  expect(orb.dataset.state).toBe('connecting')
  view.handle({ type: 'connection', status: 'connected' })
  expect(orb.dataset.state).toBe('listening')
  expect(label.textContent).toBe('Listening')
})

it('does not claim to listen while question input is automatically paused', () => {
  const { view, orb, label, hint } = setup()
  view.handle({ type: 'connection', status: 'connected' })
  view.handle({ type: 'activity', candidate_speaking: false, interviewer_playing: false,
    muted: false, input_paused: true })
  expect(label.textContent).toBe('Preparing your question')
  expect(hint.textContent).toContain('microphone')
  view.handle({ type: 'activity', candidate_speaking: false, interviewer_playing: true,
    muted: false, input_paused: true })
  expect(orb.dataset.state).toBe('speaking')
  view.handle({ type: 'activity', candidate_speaking: false, interviewer_playing: false,
    muted: false, input_paused: false })
  expect(label.textContent).toBe('Listening')
})

it('reflects actual interviewer and candidate activity, with mute taking priority', () => {
  const { view, orb, label } = setup()
  view.handle({ type: 'connection', status: 'connected' })
  view.handle({ type: 'activity', candidate_speaking: false, interviewer_playing: true, muted: false })
  expect(orb.dataset.state).toBe('speaking')
  view.handle({ type: 'activity', candidate_speaking: true, interviewer_playing: false, muted: false })
  expect(orb.dataset.state).toBe('user-speaking')
  view.handle({ type: 'activity', candidate_speaking: true, interviewer_playing: true, muted: true })
  expect(orb.dataset.state).toBe('muted')
  expect(label.textContent).toBe('Microphone muted')
})

it('keeps terminal and failed states when cleanup emits disconnected', () => {
  const { view, orb, label } = setup()
  view.handle({ type: 'connection', status: 'failed' })
  view.handle({ type: 'connection', status: 'disconnected' })
  expect(orb.dataset.state).toBe('error')
  view.ready()
  view.handle({ type: 'finished', interview: { ...interviewFixture(), phase: 'completed' } })
  view.handle({ type: 'connection', status: 'disconnected' })
  view.handle({ type: 'activity', candidate_speaking: true, interviewer_playing: true, muted: false })
  expect(orb.dataset.state).toBe('finished')
  expect(label.textContent).toBe('Session complete')
})

it('retains the speaking state for a recoverable warning instead of faking disconnection', () => {
  const { view, orb } = setup()
  view.handle({ type: 'connection', status: 'connected' })
  view.handle({ type: 'activity', candidate_speaking: false, interviewer_playing: true, muted: false })
  view.handle({ type: 'error', code: 'audio_playback_blocked', message: 'Enable audio', retryable: true })
  expect(orb.dataset.state).toBe('speaking')
})
