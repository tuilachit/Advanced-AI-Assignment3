import { RealtimeVoiceController } from './controller'
import { interviewApi } from './interviewApi'
import { TranscriptView } from './transcriptView'
import { VoiceOrbView } from './orbView'
import type { Interview, VoiceEvent } from './types'

const root = import.meta.env.VITE_API_ROOT ?? 'http://127.0.0.1:8010/api'
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const button = (id: string) => element<HTMLButtonElement>(id)
const consent = element<HTMLInputElement>('consent')
let interview: Interview | null = null
let controller: RealtimeVoiceController | null = null
let muted = false
const transcript = new TranscriptView(element('transcript'))
const orb = new VoiceOrbView(element('voice-orb'), element('voice-status'), element('voice-hint'))

function fail(message: string) { element('error').textContent = message }

function update(event: VoiceEvent) {
  orb.handle(event)
  element('state').textContent = JSON.stringify(event, null, 2)
  if (event.type === 'connection') {
    const terminal = interview && !['ready', 'active'].includes(interview.phase) ? interview : null
    element('status').textContent = terminal ? `${terminal.phase} · ${terminal.end_reason}` : event.status
    const connected = event.status === 'connected'
    for (const id of ['mute', 'audio', 'skip']) button(id).disabled = !connected
    button('connect').disabled = !interview || Boolean(terminal) || connected || event.status === 'connecting'
    if (event.status === 'failed') button('connect').textContent = 'Reconnect voice'
  } else if (event.type === 'transcript') {
    transcript.update(event.turn)
  } else if (event.type === 'activity') {
    muted = event.muted
    button('mute').setAttribute('aria-label', muted ? 'Unmute microphone' : 'Mute microphone')
    button('mute').setAttribute('title', muted ? 'Unmute microphone' : 'Mute microphone')
    button('mute').setAttribute('aria-pressed', String(muted))
    element('activity').textContent = event.muted ? 'Microphone muted'
      : event.candidate_speaking ? 'Listening to you…'
        : event.interviewer_playing ? 'Interviewer speaking…'
          : event.input_paused ? 'Microphone paused until the question finishes.' : 'Listening — take your time.'
  } else if (event.type === 'question') element('question').textContent = event.question.text
  else if (event.type === 'error') fail(event.message)
  else if (event.type === 'finished') {
    interview = event.interview
    element('status').textContent = `${interview.phase} · ${interview.end_reason}`
    button('connect').disabled = true
    button('finish').disabled = true
    for (const id of ['mute', 'audio', 'skip']) button(id).disabled = true
  }
}

button('prepare').onclick = async () => {
  if (!consent.checked) { fail('Please agree to audio and transcript use first.'); return }
  button('prepare').disabled = true
  fail('')
  controller?.disconnect()
  try {
    const response = await fetch(`${root}/voice-demo`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ send_audio_to_provider: true, retain_transcript_for_feedback: true }) })
    if (!response.ok) throw new Error('Demo setup failed. Start scripts/voice_dev_server.py and try again.')
    interview = await response.json() as Interview
    controller = new RealtimeVoiceController(interviewApi(interview.session_id, root))
    controller.subscribe(update)
    orb.ready()
    transcript.clear()
    element('context').textContent = `Synthetic Maya profile / ${interview.job.title} / ${interview.interview_id}`
    button('connect').disabled = false
    button('connect').textContent = 'Start voice interview'
    element('status').textContent = 'Ready'
  } catch (error) { fail(error instanceof Error ? error.message : 'Demo setup failed.') }
  finally { button('prepare').disabled = false }
}

button('connect').onclick = async () => {
  if (!controller || !interview || !consent.checked) return
  fail('')
  muted = false
  button('mute').setAttribute('aria-label', 'Mute microphone')
  button('mute').setAttribute('title', 'Mute microphone')
  button('mute').setAttribute('aria-pressed', 'false')
  try {
    await controller.connect(interview.interview_id)
    button('finish').disabled = false
  } catch { /* The controller emits a safe, actionable error. */ }
}
button('mute').onclick = () => {
  muted = !muted
  controller?.set_muted(muted)
  button('mute').setAttribute('aria-label', muted ? 'Unmute microphone' : 'Mute microphone')
  button('mute').setAttribute('title', muted ? 'Unmute microphone' : 'Mute microphone')
  button('mute').setAttribute('aria-pressed', String(muted))
}
button('audio').onclick = () => { fail(''); void controller?.resume_audio() }
button('skip').onclick = async () => {
  try { await controller?.skip() } catch { fail('Question could not be skipped. Reconnect and retry.') }
}
button('finish').onclick = async () => {
  button('finish').disabled = true
  try {
    const result = await controller?.finish()
    if (result?.phase === 'finalizing') element('activity').textContent = 'Finishing — waiting for the last transcript…'
  } catch {
    button('finish').disabled = false
    fail('Finishing failed. Check that the API is running and retry.')
  }
}
window.addEventListener('beforeunload', () => controller?.disconnect())
