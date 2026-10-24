import type { VoiceEvent } from './types'

type OrbState = 'idle' | 'ready' | 'connecting' | 'listening' | 'speaking' | 'user-speaking' | 'muted' | 'error' | 'finished'

const copy: Record<OrbState, [string, string]> = {
  idle: ['A space to find your voice', 'Prepare the demo below. Your microphone stays off until you start.'],
  ready: ['Ready when you are', 'Start your interview, take a breath, and speak naturally.'],
  connecting: ['Connecting', 'Getting your microphone and interviewer ready…'],
  listening: ['Listening', 'Take your time. There’s no need to rush.'],
  speaking: ['Your interviewer is speaking', 'Listen, then answer in your own words.'],
  'user-speaking': ['You have the floor', 'Keep going. Your live caption will settle into a final transcript.'],
  muted: ['Microphone muted', 'Unmute whenever you’re ready to continue.'],
  error: ['Connection needs attention', 'Check the message below, then reconnect when you’re ready.'],
  finished: ['Session complete', 'A little practice, a little more confidence. Your transcript is below.'],
}

export class VoiceOrbView {
  private connected = false
  private prepared = false
  private terminal = false

  constructor(private orb: HTMLElement, private label: HTMLElement, private hint: HTMLElement) { this.show('idle') }

  ready(): void {
    this.connected = false
    this.prepared = true
    this.terminal = false
    this.show('ready')
  }

  handle(event: VoiceEvent): void {
    if (this.terminal) return
    if (event.type === 'finished') {
      this.terminal = true
      this.connected = false
      this.show(event.interview.phase === 'failed' ? 'error' : 'finished')
      if (event.interview.phase === 'cancelled') this.label.textContent = 'Session cancelled'
    } else if (event.type === 'connection') {
      this.connected = event.status === 'connected'
      if (event.status === 'failed') this.show('error')
      else if (event.status === 'connecting') this.show('connecting')
      else if (event.status === 'connected') this.show('listening')
      else if (this.orb.dataset.state !== 'error') this.show(this.prepared ? 'ready' : 'idle')
    } else if (event.type === 'activity' && this.connected) {
      this.show(event.muted ? 'muted' : event.candidate_speaking ? 'user-speaking'
        : event.interviewer_playing ? 'speaking' : 'listening')
    }
  }

  private show(state: OrbState): void {
    this.orb.dataset.state = state
    const [label, hint] = copy[state]
    if (this.label.textContent !== label) this.label.textContent = label
    if (this.hint.textContent !== hint) this.hint.textContent = hint
  }
}
