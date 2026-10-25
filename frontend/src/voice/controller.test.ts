import { expect, it, vi } from 'vitest'

import { RealtimeVoiceController, type VoicePlatform } from './controller'
import { interviewApi } from './interviewApi'
import { interviewFixture } from './testFixtures'
import type { VoiceEvent } from './types'

function platform(denyMicrophone = false, denySdp = false) {
  let stopped = false
  let closed = false
  let tokenExposed = false
  const sent: Record<string, unknown>[] = []
  const track = { enabled: true, stop: () => { stopped = true } }
  const channel = Object.assign(new EventTarget(), { readyState: 'open',
    send: (value: string) => { sent.push(JSON.parse(value)) }, close: () => {} })
  const peer = Object.assign(new EventTarget(), { addTrack: () => {}, close: () => { closed = true },
    createDataChannel: () => channel, createOffer: async () => ({ type: 'offer', sdp: 'fixture-sdp' }),
    setLocalDescription: async () => {}, setRemoteDescription: async () => {},
    connectionState: 'connected' })
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
  const audio = { play: async () => {}, pause: () => {}, paused: false,
    muted: false, srcObject: null, autoplay: true }
  const impl: VoicePlatform = {
    get_user_media: async () => {
      if (denyMicrophone) throw new DOMException('Permission denied', 'NotAllowedError')
      return stream as unknown as MediaStream
    },
    create_peer: () => peer as unknown as RTCPeerConnection,
    create_audio: () => audio as unknown as HTMLAudioElement,
    fetch: async (_url, options) => {
      tokenExposed = String(options?.headers).includes('permanent-key')
      return new Response(denySdp ? 'private upstream error' : 'fixture-answer', { status: denySdp ? 503 : 201 })
    },
  }
  return { impl, track, channel, peer, audio, stream, sent, stopped: () => stopped, closed: () => closed,
    tokenExposed: () => tokenExposed }
}

it('does not start or request a credential when microphone permission is denied', async () => {
  const device = platform(true)
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(interviewApi('s1'), device.impl)
  controller.subscribe((event) => events.push(event))
  await expect(controller.connect('i1')).rejects.toThrow()
  expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'microphone_denied' }))
  expect(events).toContainEqual({ type: 'connection', status: 'failed' })
})

function voiceApi() {
  return { ...interviewApi('s1'), get: async () => interviewFixture(),
    token: async () => ({ client_secret: 'ephemeral-fixture', expires_at: 4_000_000_000,
      connection_id: 'c1', model: 'gpt-realtime-2' }),
    turn: async () => ({ event_id: 'e1', turn_id: 't1', transcript_revision: 1 }) }
}

it('gates microphone input before connecting and until actual question playback stops', async () => {
  const device = platform()
  let enabledAtRead: boolean | undefined
  const api = { ...voiceApi(), get: async () => { enabledAtRead = device.track.enabled; return interviewFixture() } }
  const controller = new RealtimeVoiceController(api, device.impl)
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    expect(enabledAtRead).toBe(false)
    expect(device.track.enabled).toBe(false)
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'question', metadata: request.metadata } })
    emit({ type: 'response.output_item.added', response_id: 'question', item: { id: 'a1', type: 'message', role: 'assistant' } })
    emit({ type: 'output_audio_buffer.started', response_id: 'question' })
    emit({ type: 'response.done', response: { id: 'question', status: 'completed', output: [] } })
    expect(device.track.enabled).toBe(false)
    emit({ type: 'output_audio_buffer.stopped', response_id: 'foreign-response' })
    expect(device.track.enabled).toBe(false)
    emit({ type: 'output_audio_buffer.stopped', response_id: 'question' })
    expect(device.track.enabled).toBe(true)
  } finally { controller.disconnect() }
})

it('fails closed and releases hardware when question playback completion never arrives', async () => {
  vi.useFakeTimers()
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  try {
    await controller.connect('i1')
    await vi.advanceTimersByTimeAsync(61000)
    expect(device.stopped()).toBe(true)
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'voice_response_failed' }))
    expect(events.at(-1)).toEqual({ type: 'connection', status: 'failed' })
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(1)
  } finally { controller.disconnect(); vi.useRealTimers() }
})

it('requires explicit recovery if the provider cancels protected question playback', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'question', metadata: request.metadata } })
    emit({ type: 'response.done', response: { id: 'question', status: 'cancelled', output: [] } })
    expect(device.stopped()).toBe(true)
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'voice_response_failed' }))
  } finally { controller.disconnect() }
})

it('gates a reconnected interview independently of late playback events from the old connection', async () => {
  const device = platform()
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const oldRequest = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'old', metadata: oldRequest.metadata } })
    emit({ type: 'output_audio_buffer.stopped', response_id: 'old' })
    expect(device.track.enabled).toBe(true)
    controller.disconnect()
    await controller.connect('i1')
    expect(device.track.enabled).toBe(false)
    emit({ type: 'output_audio_buffer.stopped', response_id: 'old' })
    expect(device.track.enabled).toBe(false)
    const request = device.sent.filter(event => event.type === 'response.create').at(-1)!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'new', metadata: request.metadata } })
    emit({ type: 'output_audio_buffer.stopped', response_id: 'new' })
    expect(device.track.enabled).toBe(true)
  } finally { controller.disconnect() }
})

it('preserves manual mute separately from the temporary question input gate', async () => {
  const device = platform()
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'question', metadata: request.metadata } })
    controller.set_muted(true)
    controller.set_muted(false)
    expect(device.track.enabled).toBe(false)
    controller.set_muted(true)
    emit({ type: 'output_audio_buffer.stopped', response_id: 'question' })
    expect(device.track.enabled).toBe(false)
    controller.set_muted(false)
    expect(device.track.enabled).toBe(true)
  } finally { controller.disconnect() }
})

it('does not let an old playback-stop event enable input for the skipped-to question', async () => {
  const device = platform()
  const first = interviewFixture().questions[0]
  const api = { ...voiceApi(), skip: async () => ({ action: 'ask_question' as const,
    question: { ...first, question_id: 'q2', text: 'Why SQL?' }, flow_revision: 2 }) }
  const controller = new RealtimeVoiceController(api, device.impl)
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'old', metadata: request.metadata } })
    emit({ type: 'response.output_item.added', response_id: 'old', item: { id: 'a1', type: 'message', role: 'assistant' } })
    emit({ type: 'output_audio_buffer.started', response_id: 'old' })
    emit({ type: 'response.done', response: { id: 'old', status: 'completed', output: [] } })
    await controller.skip()
    expect(device.sent).toContainEqual({ type: 'output_audio_buffer.clear' })
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(2)
    emit({ type: 'output_audio_buffer.stopped', response_id: 'old' })
    expect(device.track.enabled).toBe(false)
  } finally { controller.disconnect() }
})

it('speaks the first issued question automatically once the remote audio is playable', async () => {
  const device = platform()
  device.audio.paused = true
  device.audio.play = async () => { device.audio.paused = false }
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  try {
    await controller.connect('i1')
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(0)
    device.peer.dispatchEvent(Object.assign(new Event('track'), { streams: [device.stream] }))
    await Promise.resolve()
    expect(device.sent.filter(event => event.type === 'response.create')).toEqual([
      expect.objectContaining({ response: expect.objectContaining({
        metadata: expect.objectContaining({ question_id: 'q1', connection_id: 'c1',
          speech_request_id: expect.any(String) }), output_modalities: ['audio'], tool_choice: 'none',
      }) }),
    ])
    await controller.resume_audio()
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(1)
  } finally { controller.disconnect() }
})

it('does not lose a question behind blocked autoplay and speaks it after Enable audio', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  device.audio.paused = true
  device.audio.play = async () => { throw new DOMException('Blocked', 'NotAllowedError') }
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  try {
    await controller.connect('i1')
    device.peer.dispatchEvent(Object.assign(new Event('track'), { streams: [device.stream] }))
    await Promise.resolve()
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'audio_playback_blocked' }))
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(0)
    device.audio.play = async () => { device.audio.paused = false }
    await controller.resume_audio()
    expect(device.sent.filter(event => event.type === 'response.create')).toHaveLength(1)
  } finally { controller.disconnect() }
})

it('ignores a late playback rejection from a disconnected interview', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  let rejectPlayback!: (reason: unknown) => void
  device.audio.play = () => new Promise<void>((_resolve, reject) => { rejectPlayback = reject })
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  await controller.connect('i1')
  const playing = controller.resume_audio()
  controller.disconnect()
  rejectPlayback(new DOMException('Old blocked playback', 'NotAllowedError'))
  await playing
  expect(events.at(-1)).toEqual({ type: 'connection', status: 'disconnected' })
  expect(events.some(event => event.type === 'error')).toBe(false)
})

it('keeps the channel open for pending transcripts while the backend is finalizing', async () => {
  vi.useFakeTimers()
  const device = platform()
  let phase: 'active' | 'finalizing' | 'completed' = 'active'
  const controller = new RealtimeVoiceController({ ...voiceApi(), get: async () => ({ ...interviewFixture(), phase }) }, device.impl)
  try {
    await controller.connect('i1')
    phase = 'finalizing'
    await vi.advanceTimersByTimeAsync(2000)
    expect(device.stopped()).toBe(false)
    expect(device.track.enabled).toBe(false)
    controller.set_muted(false)
    expect(device.track.enabled).toBe(false)
    phase = 'completed'
    await vi.advanceTimersByTimeAsync(2000)
    expect(device.stopped()).toBe(true)
  } finally { controller.disconnect(); vi.useRealTimers() }
})

it('does not report completion when the end route still has transcripts to finalize', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController({ ...voiceApi(), end: async () => ({ ...interviewFixture(), phase: 'finalizing' }) }, device.impl)
  controller.subscribe(event => events.push(event))
  try {
    await controller.connect('i1')
    expect((await controller.finish()).phase).toBe('finalizing')
    expect(device.stopped()).toBe(false)
    expect(events.some(event => event.type === 'finished')).toBe(false)
  } finally { controller.disconnect() }
})

it('cleans up and exposes recovery when an established data channel closes', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  try {
    await controller.connect('i1')
    device.channel.dispatchEvent(new Event('close'))
    expect(device.stopped()).toBe(true)
    expect(events.at(-1)).toEqual({ type: 'connection', status: 'failed' })
  } finally { controller.disconnect() }
})

it('keeps actual interviewer activity across mute and unmute', async () => {
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'r1', metadata: request.metadata } })
    emit({ type: 'response.output_item.added', response_id: 'r1', item: { id: 'a1', type: 'message', role: 'assistant' } })
    emit({ type: 'output_audio_buffer.started', response_id: 'r1' })
    controller.set_muted(true)
    controller.set_muted(false)
    expect(events.at(-1)).toMatchObject({ type: 'activity', interviewer_playing: true, muted: false })
  } finally { controller.disconnect() }
})

it('disconnects a failed transcript engine so the existing interview can be reconnected', async () => {
  vi.useFakeTimers()
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController({ ...voiceApi(), turn: async () => { throw new Error('Unavailable') } }, device.impl)
  controller.subscribe(event => events.push(event))
  try {
    await controller.connect('i1')
    device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'input_audio_buffer.speech_started', item_id: 'u1' }) }))
    await vi.advanceTimersByTimeAsync(1000)
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'transcript_save_failed' }))
    expect(events.at(-1)).toEqual({ type: 'connection', status: 'failed' })
    expect(device.stopped()).toBe(true)
  } finally { controller.disconnect(); vi.useRealTimers() }
})

it('makes reconnect available after a missing-final-transcript timeout', async () => {
  vi.useFakeTimers()
  const device = platform()
  const events: VoiceEvent[] = []
  const controller = new RealtimeVoiceController(voiceApi(), device.impl)
  controller.subscribe(event => events.push(event))
  const emit = (event: unknown) => device.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  try {
    await controller.connect('i1')
    const request = device.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    emit({ type: 'response.created', response: { id: 'question', metadata: request.metadata } })
    emit({ type: 'response.done', response: { id: 'question', status: 'completed', output: [] } })
    emit({ type: 'output_audio_buffer.stopped', response_id: 'question' })
    emit({ type: 'input_audio_buffer.speech_started', item_id: 'u1' })
    emit({ type: 'input_audio_buffer.speech_stopped', item_id: 'u1' })
    emit({ type: 'response.done', response: { id: 'tool', status: 'completed', output: [
      { type: 'function_call', name: 'advance_interview', call_id: 'timeout-call', arguments: '{"follow_up_question":"","follow_up_rationale":""}' },
    ] } })
    await vi.advanceTimersByTimeAsync(11000)
    expect(events.at(-1)).toEqual({ type: 'connection', status: 'failed' })
    expect(device.stopped()).toBe(true)
  } finally { controller.disconnect(); vi.useRealTimers() }
})

it('releases microphone and peer and redacts a failed SDP response', async () => {
  const device = platform(false, true)
  const events: VoiceEvent[] = []
  const api = { ...interviewApi('s1'), get: async () => interviewFixture(),
    token: async () => ({ client_secret: 'ephemeral-fixture', expires_at: 4_000_000_000,
      connection_id: 'c1', model: 'gpt-realtime-2' }) }
  const controller = new RealtimeVoiceController(api, device.impl)
  controller.subscribe((event) => events.push(event))
  await expect(controller.connect('i1')).rejects.toThrow()
  expect(device.stopped()).toBe(true)
  expect(device.closed()).toBe(true)
  expect(JSON.stringify(events)).not.toContain('private upstream error')
  expect(JSON.stringify(events)).not.toContain('ephemeral-fixture')
})
