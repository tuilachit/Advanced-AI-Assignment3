import { preparedInterview } from '../../../test/interviewFixtures'
import type { Interview, TranscriptTurn } from '../../../types'
import type { VoiceController, VoiceIntegration, VoiceNotification } from '../live/voiceBridge'

// Scripted, synthetic UI review only. Not imported by the application entry point;
// never accesses a microphone, persists a turn, or contacts an API/provider.
export function previewInterview(): Interview {
  const interview = preparedInterview({ request_id: 'ui-preview', job: { source: 'pasted_job', title: 'Graduate Software Engineer',
    description: 'Build reliable software in a collaborative team.' },
    consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true } })
  const questions = [
    'Tell me about a project where you had to make a difficult technical decision.',
    'How did you work with others to resolve a disagreement in your team?',
    'How would you test an API before releasing it to users?',
    'What would you do differently if you built your project again?',
  ]
  return { ...interview, questions: interview.questions.map((question, index) => ({ ...question, text: questions[index] })) }
}

export class PreviewVoiceController implements VoiceController {
  interview = previewInterview()
  private listeners = new Set<(event: VoiceNotification) => void>()
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private muted = false
  private playing = false
  private talking = false
  private turnCounter = 0

  subscribe(listener: (event: VoiceNotification) => void) { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  emit(event: VoiceNotification) { for (const listener of this.listeners) listener(event) }
  private later(action: () => void, delay: number) {
    const timer = setTimeout(() => { this.timers.delete(timer); action() }, delay)
    this.timers.add(timer)
  }
  private clear() { this.timers.forEach(clearTimeout); this.timers.clear() }
  private activity() { this.emit({ type: 'activity', candidate_speaking: this.talking, interviewer_playing: this.playing, muted: this.muted }) }
  private caption(turn: TranscriptTurn) {
    const index = this.interview.turns.findIndex((item) => item.turn_id === turn.turn_id)
    if (index < 0) this.interview.turns.push(turn)
    else this.interview.turns[index] = turn
    this.interview.transcript_revision++
    this.emit({ type: 'transcript', turn })
  }
  private playExample() {
    const question = this.interview.questions.find((item) => item.question_id === this.interview.current_question_id)!
    this.emit({ type: 'question', question, flow_revision: this.interview.flow_revision })
    const questionTurn: TranscriptTurn = { turn_id: 'preview-question-' + ++this.turnCounter,
      question_id: question.question_id, speaker: 'interviewer', input_mode: 'live_voice', transcript_version: 1,
      transcript_status: 'final', text: question.text, delivery_status: 'complete', timing: null }
    this.playing = true
    this.talking = false
    this.activity()
    this.caption(questionTurn)
    const candidateTurn: TranscriptTurn = { ...questionTurn, turn_id: 'preview-answer-' + this.turnCounter,
      speaker: 'candidate', transcript_status: 'partial', text: 'In our course-planning project,', delivery_status: 'not_applicable' }
    this.later(() => {
      this.playing = false
      this.talking = !this.muted
      this.activity()
      this.caption(candidateTurn)
    }, 1700)
    this.later(() => {
      this.caption({ ...candidateTurn, transcript_version: 2, transcript_status: 'final',
        text: 'In our course-planning project, I compared two API designs. I built a small prototype, reviewed the trade-offs with my team, and chose the simpler option to make testing easier.' })
      this.talking = false
      this.activity()
    }, 3300)
  }
  async connect() {
    this.clear()
    this.emit({ type: 'connection', status: 'connecting' })
    this.later(() => {
      if (this.interview.phase === 'ready') {
        this.interview = { ...this.interview, phase: 'active', started_at: new Date().toISOString(), flow_revision: 1,
          current_question_id: this.interview.questions[0].question_id }
        this.interview.questions[0].status = 'issued'
      }
      this.muted = false
      this.emit({ type: 'connection', status: 'connected' })
      this.playExample()
    }, 650)
  }
  set_muted(muted: boolean) { this.muted = muted; this.activity() }
  async resume_audio() { this.activity() }
  async skip() {
    this.clear()
    const index = this.interview.questions.findIndex((question) => question.question_id === this.interview.current_question_id)
    this.interview.questions[index].status = 'skipped'
    if (index === this.interview.questions.length - 1) { await this.finish(); return }
    this.interview.questions[index + 1].status = 'issued'
    this.interview.current_question_id = this.interview.questions[index + 1].question_id
    this.interview.flow_revision++
    this.playExample()
  }
  async finish() {
    this.clear()
    this.set_muted(true)
    this.interview = { ...this.interview, phase: 'finalizing', flow_revision: this.interview.flow_revision + 1 }
    this.later(() => {
      this.interview = { ...this.interview, phase: 'completed', flow_revision: this.interview.flow_revision + 1,
        ended_at: new Date().toISOString(), end_reason: 'user_finished' }
      this.emit({ type: 'finished', interview: structuredClone(this.interview) })
      this.disconnect()
    }, 1500)
    return structuredClone(this.interview)
  }
  disconnect() { this.clear(); this.muted = true; this.playing = false; this.talking = false; this.emit({ type: 'connection', status: 'disconnected' }) }
  simulateFailure(code: 'voice_disconnected' | 'microphone_denied' | 'audio_playback_blocked') {
    const messages = {
      voice_disconnected: 'The voice connection was lost. Your saved transcript is kept; reconnect to continue.',
      microphone_denied: 'Microphone access was denied. Allow it in your browser and retry.',
      audio_playback_blocked: 'Your browser blocked audio playback. Press Enable audio to listen.',
    }
    if (code !== 'audio_playback_blocked') this.disconnect()
    this.emit({ type: 'error', code, message: messages[code], retryable: true })
    if (code !== 'audio_playback_blocked') this.emit({ type: 'connection', status: 'failed' })
  }
  integration: VoiceIntegration = {
    createController: () => this,
    readInterview: async () => structuredClone(this.interview),
  }
}
