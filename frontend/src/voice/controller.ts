import type { Interview, InterviewApi, VoiceEvent } from './types'
import { InterviewVoiceSession } from './voiceSession'

export interface VoicePlatform {
  get_user_media(): Promise<MediaStream>
  create_peer(): RTCPeerConnection
  create_audio(): HTMLAudioElement
  fetch: typeof fetch
}

function browserPlatform(): VoicePlatform {
  return {
    get_user_media: () => navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    }),
    create_peer: () => new RTCPeerConnection(),
    create_audio: () => { const audio = document.createElement('audio'); audio.autoplay = true; return audio },
    fetch: (...args) => fetch(...args),
  }
}

export class RealtimeVoiceController {
  private api: InterviewApi
  private platform: VoicePlatform
  private listeners = new Set<(event: VoiceEvent) => void>()
  private peer: RTCPeerConnection | null = null
  private channel: RTCDataChannel | null = null
  private stream: MediaStream | null = null
  private audio: HTMLAudioElement | null = null
  private engine: InterviewVoiceSession | null = null
  private poll: ReturnType<typeof setInterval> | undefined
  private epoch = 0
  private connecting = false
  private muted = false
  private inputPaused = true
  private finalizing = false
  private activity = { candidate_speaking: false, interviewer_playing: false }
  private interviewId: string | null = null
  private abort: AbortController | null = null

  constructor(api: InterviewApi, platform = browserPlatform()) {
    this.api = api
    this.platform = platform
  }

  subscribe(listener: (event: VoiceEvent) => void): () => void {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private emit(event: VoiceEvent): void {
    if (event.type === 'activity') {
      this.activity = { candidate_speaking: event.candidate_speaking, interviewer_playing: event.interviewer_playing }
      event = { ...event, muted: this.muted, input_paused: this.inputPaused,
        candidate_speaking: event.candidate_speaking && !this.inputPaused }
    }
    for (const listener of this.listeners) listener(event)
  }

  private cleanup(): void {
    clearInterval(this.poll)
    this.abort?.abort()
    this.abort = null
    this.engine?.close()
    this.engine = null
    const channel = this.channel
    this.channel = null
    channel?.close()
    this.peer?.close()
    this.peer = null
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.audio?.pause()
    if (this.audio) this.audio.srcObject = null
    this.audio = null
    this.activity = { candidate_speaking: false, interviewer_playing: false }
    this.inputPaused = true
  }

  async connect(id: string): Promise<void> {
    if (this.connecting) throw new Error('A voice connection is already being prepared.')
    this.connecting = true
    this.cleanup()
    const epoch = ++this.epoch
    this.interviewId = id
    this.muted = false
    this.finalizing = false
    this.emit({ type: 'connection', status: 'connecting' })
    const check = () => {
      if (epoch !== this.epoch) throw new DOMException('Connection cancelled', 'AbortError')
    }
    try {
      const stream = await this.platform.get_user_media()
      if (epoch !== this.epoch) { stream.getTracks().forEach((track) => track.stop()); check() }
      this.stream = stream
      this.syncInput()
      let interview = await this.api.get(id)
      check()
      if (interview.phase === 'ready') {
        interview = (await this.api.start(id, {
          request_id: crypto.randomUUID(), expected_flow_revision: interview.flow_revision,
        })).interview
      }
      check()
      if (interview.phase !== 'active') throw new Error('Interview is not active.')
      const credential = await this.api.token(id)
      check()
      if (credential.expires_at * 1000 <= Date.now()) throw new Error('Expired voice credential.')
      const peer = this.platform.create_peer()
      this.peer = peer
      this.audio = this.platform.create_audio()
      const channel = peer.createDataChannel('interview-events')
      this.channel = channel
      const failConnection = () => {
        if (epoch !== this.epoch || this.channel !== channel) return
        this.epoch++
        this.cleanup()
        this.emit({ type: 'error', code: 'voice_disconnected',
          message: 'The voice connection was lost. Your saved transcript is kept; reconnect to continue.', retryable: true })
        this.emit({ type: 'connection', status: 'failed' })
      }
      channel.addEventListener('close', failConnection)
      channel.addEventListener('error', failConnection)
      const engine = new InterviewVoiceSession({
        interview, connection_id: credential.connection_id, api: this.api,
        send: (event) => {
          if (epoch === this.epoch && channel.readyState === 'open') channel.send(JSON.stringify(event))
        },
        emit: (event) => {
          if (epoch !== this.epoch) return
          this.emit(event)
          if (event.type === 'finished') this.disconnect()
          else if (event.type === 'error' && ['transcript_save_failed', 'interview_step_failed',
            'unissued_question', 'voice_response_failed', 'voice_provider_error', 'transcript_timeout'].includes(event.code)) {
            // A fresh engine is required; release the mic and re-enable the UI's connect action.
            this.epoch++
            this.cleanup()
            this.emit({ type: 'connection', status: 'failed' })
          }
        },
        can_hear_audio: () => Boolean(this.audio && !this.audio.paused && !this.audio.muted),
        set_input_paused: (paused) => {
          if (epoch !== this.epoch) return
          this.inputPaused = paused
          this.syncInput()
          this.emit({ type: 'activity', ...this.activity, muted: this.muted })
        },
      })
      this.engine = engine
      for (const track of stream.getTracks()) peer.addTrack(track, stream)
      peer.addEventListener('track', (event) => {
        if (epoch !== this.epoch || !this.audio) return
        this.audio.srcObject = event.streams[0] ?? new MediaStream([event.track])
        void this.resume_audio()
      })
      channel.addEventListener('message', (event) => {
        if (epoch !== this.epoch) return
        try {
          const parsed: unknown = JSON.parse(String(event.data))
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            engine.handle(parsed as Record<string, unknown>)
          }
        } catch {
          this.emit({ type: 'error', code: 'invalid_voice_event',
            message: 'An unreadable voice event was ignored.', retryable: true })
        }
      })
      peer.addEventListener('connectionstatechange', () => {
        if (epoch !== this.epoch) return
        if (['failed', 'disconnected'].includes(peer.connectionState)) {
          failConnection()
        }
      })
      const offer = await peer.createOffer()
      check()
      await peer.setLocalDescription(offer)
      check()
      this.abort = new AbortController()
      const response = await this.platform.fetch('https://api.openai.com/v1/realtime/calls', {
        method: 'POST', body: offer.sdp,
        headers: { Authorization: `Bearer ${credential.client_secret}`, 'Content-Type': 'application/sdp' },
        signal: AbortSignal.any([this.abort.signal, AbortSignal.timeout(15_000)]),
      })
      check()
      if (!response.ok) throw new Error('The provider rejected the voice connection.')
      const sdp = await response.text()
      check()
      await peer.setRemoteDescription({ type: 'answer', sdp })
      check()
      await new Promise<void>((resolve, reject) => {
        if (channel.readyState === 'open') { resolve(); return }
        const timer = setTimeout(() => reject(new Error('Voice data channel timed out.')), 10_000)
        channel.addEventListener('open', () => { clearTimeout(timer); resolve() }, { once: true })
        channel.addEventListener('close', () => {
          clearTimeout(timer); reject(new Error('Voice data channel closed.'))
        }, { once: true })
      })
      check()
      this.emit({ type: 'connection', status: 'connected' })
      const question = interview.questions.find((q) => q.question_id === interview.current_question_id)
      if (question) this.emit({ type: 'question', question, flow_revision: interview.flow_revision })
      engine.askCurrentQuestion()
      this.poll = setInterval(() => {
        void this.api.get(id).then((state) => {
          if (epoch !== this.epoch) return
          if (state.phase === 'finalizing') {
            // Retain the data channel for Tien's pending-ASR drain; accept no new speech.
            this.finalizing = true
            engine.beginFinalizing()
            if (!this.muted) this.set_muted(true)
          } else if (state.phase !== 'active') {
            this.emit({ type: 'finished', interview: state })
            this.disconnect()
          }
        }).catch(() => {
          if (epoch === this.epoch) this.emit({ type: 'error', code: 'api_unreachable',
            message: 'The local API could not be reached. Check FastAPI before continuing.', retryable: true })
        })
      }, 2000)
    } catch (error) {
      if (epoch === this.epoch) {
        const denied = error instanceof DOMException && error.name === 'NotAllowedError'
        this.cleanup()
        this.emit({ type: 'error', code: denied ? 'microphone_denied' : 'voice_connection_failed',
          message: denied ? 'Microphone access was denied. Allow it in your browser and retry.'
            : 'The voice connection could not be established. Check the local API and retry.', retryable: true })
        this.emit({ type: 'connection', status: 'failed' })
      }
      throw new Error('The voice connection could not be established.', { cause: error })
    } finally {
      this.connecting = false
    }
  }

  set_muted(muted: boolean): void {
    if (this.finalizing) muted = true
    this.muted = muted
    this.syncInput()
    this.emit({ type: 'activity', ...this.activity, muted })
  }

  private syncInput(): void {
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !this.muted && !this.inputPaused && !this.finalizing
    })
  }

  async resume_audio(): Promise<void> {
    const audio = this.audio
    const engine = this.engine
    try {
      await audio?.play()
      if (audio && audio === this.audio && engine === this.engine) engine?.resumeSpeech()
    }
    catch {
      if (audio !== this.audio || engine !== this.engine) return
      this.emit({ type: 'error', code: 'audio_playback_blocked',
        message: 'Your browser blocked audio playback. Press Enable audio; your interviewer will then speak the question.', retryable: true })
    }
  }

  async finish(): Promise<Interview> {
    this.finalizing = true
    this.set_muted(true)
    let result: Interview
    if (this.engine) result = await this.engine.finish()
    else {
      if (!this.interviewId) throw new Error('No interview is selected.')
      const current = await this.api.get(this.interviewId)
      result = current.phase === 'active' ? await this.api.end(current.interview_id, {
        request_id: crypto.randomUUID(), expected_flow_revision: current.flow_revision,
      }) : current
    }
    if (result.phase !== 'finalizing') {
      this.emit({ type: 'finished', interview: result })
      this.disconnect()
    }
    return result
  }

  async skip(): Promise<void> { if (!this.finalizing) await this.engine?.skip() }

  disconnect(): void {
    this.epoch++
    this.cleanup()
    this.emit({ type: 'connection', status: 'disconnected' })
  }
}
