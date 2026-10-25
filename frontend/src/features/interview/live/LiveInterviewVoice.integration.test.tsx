import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { components } from '../../../generated/api-schema'
import { preparedInterview } from '../../../test/interviewFixtures'
import { LiveInterviewStage } from './LiveInterviewStage'

type Schemas = components['schemas']
function ready() {
  return preparedInterview({ request_id: 'real-controller-test',
    job: { source: 'supplied_job', document_id: 'job-1' },
    consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true } })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

// Only hardware and HTTP are replaced. The default bridge, both real API
// clients, Luke's controller/session engine and the React hook run unchanged.
function harness() {
  const server = { interview: ready(), tokenUnavailable: false, endUnavailable: false,
    endPhase: 'completed' as 'completed' | 'finalizing' }
  const hardware = { denyMicrophone: false, denySdp: false, blockPlayback: false }
  const requests: { method: string; path: string; body: Record<string, unknown> }[] = []
  const media = () => {
    const track = { enabled: true, stop: vi.fn() }
    return { track, getTracks: () => [track], getAudioTracks: () => [track] }
  }
  const streams: ReturnType<typeof media>[] = []
  const getUserMedia = vi.fn(async () => {
    if (hardware.denyMicrophone) throw new DOMException('Denied', 'NotAllowedError')
    const stream = media()
    streams.push(stream)
    return stream
  })
  vi.stubGlobal('navigator', Object.create(navigator, { mediaDevices: { value: { getUserMedia } } }))
  function device() {
    const sent: Record<string, unknown>[] = []
    const channel = Object.assign(new EventTarget(), { readyState: 'open',
      send: vi.fn((data: string) => sent.push(JSON.parse(data))),
      close: vi.fn(() => { channel.readyState = 'closed' }) })
    const audio = { paused: true, muted: false, autoplay: true, srcObject: null as unknown,
      play: vi.fn(async () => {
        if (hardware.blockPlayback) throw new DOMException('Blocked', 'NotAllowedError')
        audio.paused = false
      }),
      pause: vi.fn(() => { audio.paused = true }) }
    const peer = Object.assign(new EventTarget(), {
      connectionState: 'connected', addTrack: vi.fn(), close: vi.fn(),
      createDataChannel: () => channel, createOffer: async () => ({ type: 'offer', sdp: 'mock-offer' }),
      setLocalDescription: async () => {},
      setRemoteDescription: async () => {
        peer.dispatchEvent(Object.assign(new Event('track'), { streams: [streams.at(-1)] }))
      },
    })
    const emit = (event: Record<string, unknown>) =>
      channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
    return { channel, audio, peer, emit, sent }
  }
  const devices: ReturnType<typeof device>[] = []
  vi.stubGlobal('RTCPeerConnection', function () {
    const current = device()
    devices.push(current)
    return current.peer
  })
  const createElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tag, options) =>
    tag === 'audio' ? devices.at(-1)!.audio as unknown as HTMLAudioElement : createElement(tag, options))

  const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
  const base = '/api/sessions/setup-test-session/interviews/prepared-interview'
  let delayedRead: ReturnType<typeof deferred<Response>> | null = null
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input))
    if (url.origin === 'https://api.openai.com' && url.pathname === '/v1/realtime/calls') {
      return new Response(hardware.denySdp ? 'private provider detail' : 'mock-answer',
        { status: hardware.denySdp ? 503 : 201 })
    }
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    requests.push({ method, path: url.pathname, body })
    if (url.origin !== 'http://localhost:8000') throw new Error('Unexpected backend')
    if (method === 'GET' && url.pathname === base) {
      if (delayedRead) { const pending = delayedRead; delayedRead = null; return pending.promise }
      return json(server.interview)
    }
    if (method !== 'POST') throw new Error('Unexpected method')
    const interview = server.interview
    switch (url.pathname) {
      case base + '/start':
        interview.phase = 'active'
        interview.started_at = new Date().toISOString()
        interview.flow_revision++
        interview.current_question_id = interview.questions[0].question_id
        interview.questions[0].status = 'issued'
        return json({ interview, next_step: { action: 'ask_question',
          question: interview.questions[0], flow_revision: interview.flow_revision } } satisfies Schemas['StartInterviewResponse'])
      case base + '/realtime-token':
        return server.tokenUnavailable
          ? json({ error: { code: 'provider_unavailable', message: 'Try again.', details: {} } }, 503)
          : json({ client_secret: 'ephemeral-test-only', expires_at: 4_000_000_000,
            connection_id: 'connection-' + streams.length, model: 'test-model' } satisfies Schemas['RealtimeCredential'])
      case base + '/turns': {
        const event = body as Schemas['TurnEventRequest']
        const index = interview.turns.findIndex((turn) => turn.turn_id === event.turn.turn_id)
        if (index === -1) interview.turns.push(event.turn)
        else interview.turns[index] = event.turn
        interview.transcript_revision++
        return json({ event_id: event.event_id, turn_id: event.turn.turn_id,
          transcript_revision: interview.transcript_revision } satisfies Schemas['TurnEventAck'])
      }
      case base + '/skip':
        interview.questions.find((question) => question.question_id === interview.current_question_id)!.status = 'skipped'
        interview.current_question_id = interview.questions[1].question_id
        interview.questions[1].status = 'issued'
        interview.flow_revision++
        return json({ action: 'ask_question', question: interview.questions[1],
          flow_revision: interview.flow_revision } satisfies Schemas['AskQuestionStep'])
      case base + '/end':
        if (server.endUnavailable) return json({ error: { code: 'provider_unavailable', message: 'Try again.', details: {} } }, 503)
        interview.phase = server.endPhase
        interview.flow_revision++
        if (interview.phase === 'completed') interview.ended_at = new Date().toISOString()
        return json(interview)
      default: throw new Error('Unexpected API route: ' + url.pathname)
    }
  }))
  return { server, hardware, requests, streams, devices, getUserMedia, media,
    posts: (action: string) => requests.filter((request) => request.method === 'POST' && request.path === base + '/' + action),
    delayRead: () => { delayedRead = deferred<Response>(); return delayedRead },
    json }
}

async function room() {
  const props = { interview: ready(), onClose: vi.fn(), onFeedback: vi.fn() }
  const view = render(<StrictMode><LiveInterviewStage {...props} /></StrictMode>)
  await act(async () => {})
  return { ...view, props }
}
async function click(name: string) {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })) })
}
async function tick(ms = 2000) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
async function answer(h: ReturnType<typeof harness>) {
  await act(async () => {
    const emit = h.devices.at(-1)!.emit
    emit({ type: 'input_audio_buffer.speech_started', item_id: 'candidate-1', audio_start_ms: 100 })
    emit({ type: 'input_audio_buffer.speech_stopped', item_id: 'candidate-1', audio_end_ms: 2200 })
    emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'candidate-1',
      transcript: 'I tested the Python API with my team.' })
  })
}
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-24T01:00:00Z')) })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('Live Interview with the real voice controller and mocked hardware', () => {
  it('starts explicitly, displays issued questions/activity/captions, mutes and delegates skip exactly once', async () => {
    const h = harness()
    await room()
    expect(h.getUserMedia).not.toHaveBeenCalled()
    expect(h.requests.every((request) => request.method === 'GET')).toBe(true)
    expect(screen.queryByText(/simulated interview/)).not.toBeInTheDocument()
    await click('Start interview')
    expect(h.getUserMedia).toHaveBeenCalledTimes(1)
    expect(h.posts('start')).toHaveLength(1)
    expect(h.posts('realtime-token')).toHaveLength(1)
    expect(screen.getByText('Connected', { exact: true })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Preparing your question' })).toBeVisible()
    expect(h.streams[0].track.enabled).toBe(false)
    expect(screen.getByText('Question 1 of 4', { exact: true })).toBeVisible()
    const voice = h.devices[0]
    expect(voice.sent.filter((event) => event.type === 'response.create')).toHaveLength(1)
    const request = voice.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    await act(async () => {
      voice.emit({ type: 'response.created', response: { id: 'response-1', metadata: request.metadata } })
      voice.emit({ type: 'response.output_item.added', response_id: 'response-1',
        item: { id: 'ai-1', type: 'message', role: 'assistant' } })
      voice.emit({ type: 'output_audio_buffer.started', response_id: 'response-1' })
    })
    expect(screen.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
    await click('Mute microphone')
    expect(h.streams[0].track.enabled).toBe(false)
    await click('Unmute microphone')
    expect(h.streams[0].track.enabled).toBe(false)
    expect(screen.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
    await act(async () => {
      voice.emit({ type: 'response.output_audio_transcript.done', response_id: 'response-1', item_id: 'ai-1',
        transcript: h.server.interview.questions[0].text })
      voice.emit({ type: 'output_audio_buffer.stopped', response_id: 'response-1' })
      voice.emit({ type: 'response.done', response: { id: 'response-1', status: 'completed', output: [] } })
      voice.emit({ type: 'input_audio_buffer.speech_started', item_id: 'candidate-1' })
      voice.emit({ type: 'conversation.item.input_audio_transcription.delta', item_id: 'candidate-1', delta: 'I tested' })
    })
    expect(h.streams[0].track.enabled).toBe(true)
    expect(screen.getByRole('heading', { name: 'You have the floor' })).toBeVisible()
    expect(screen.getByText('Live caption · may change')).toBeVisible()
    await answer(h)
    expect(screen.getByText('I tested the Python API with my team.')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Listening' })).toBeVisible()
    await click('Skip question')
    expect(h.posts('skip')).toHaveLength(1)
    expect(screen.getByText('Question 2 of 4', { exact: true })).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '1')
    expect(h.posts('next-step')).toHaveLength(0)
    expect(document.body.textContent).not.toContain('ephemeral-test-only')
  })

  it.each(['microphone', 'token', 'sdp'] as const)('recovers from %s failure without losing backend start state', async (failure) => {
    const h = harness()
    h.hardware.denyMicrophone = failure === 'microphone'
    h.hardware.denySdp = failure === 'sdp'
    h.server.tokenUnavailable = failure === 'token'
    await room()
    await click('Start interview')
    expect(screen.getByRole('alert')).toHaveTextContent(failure === 'microphone' ? 'Microphone access was denied' : 'could not be established')
    expect(screen.getByText('Microphone off', { exact: true })).toBeVisible()
    if (failure === 'microphone') {
      expect(h.posts('start')).toHaveLength(0)
      expect(h.posts('realtime-token')).toHaveLength(0)
    } else {
      expect(h.streams[0].track.stop).toHaveBeenCalled()
      await tick()
      expect(screen.getByRole('timer')).toHaveTextContent('09:58')
    }
    h.hardware.denyMicrophone = h.hardware.denySdp = h.server.tokenUnavailable = false
    await click(failure === 'microphone' ? 'Start interview' : 'Reconnect voice')
    expect(screen.getByText('Connected', { exact: true })).toBeVisible()
    expect(h.posts('start')).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps blocked playback recoverable and asks the waiting question only after audio is enabled', async () => {
    const h = harness()
    h.hardware.blockPlayback = true
    await room()
    await click('Start interview')
    expect(screen.getByRole('alert')).toHaveTextContent('blocked audio playback')
    expect(h.devices[0].sent).toHaveLength(0)
    await click('Enable audio')
    expect(screen.getByRole('button', { name: 'Enable audio' })).toBeEnabled()
    h.hardware.blockPlayback = false
    await click('Enable audio')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(h.devices[0].sent.filter((event) => event.type === 'response.create')).toHaveLength(1)
    expect(h.posts('start')).toHaveLength(1)
  })

  it('releases a lost connection and reconnects explicitly with saved captions and no second start', async () => {
    const h = harness()
    await room()
    await click('Start interview')
    await answer(h)
    act(() => h.devices[0].channel.dispatchEvent(new Event('close')))
    expect(screen.getByText('Connection lost', { exact: true })).toBeVisible()
    expect(h.streams[0].track.stop).toHaveBeenCalled()
    expect(h.devices[0].peer.close).toHaveBeenCalled()
    expect(h.devices[0].audio.srcObject).toBeNull()
    await tick()
    expect(h.getUserMedia).toHaveBeenCalledTimes(1)
    await click('Reconnect voice')
    expect(h.getUserMedia).toHaveBeenCalledTimes(2)
    expect(h.posts('start')).toHaveLength(1)
    expect(h.posts('realtime-token')).toHaveLength(2)
    expect(screen.getByText('I tested the Python API with my team.')).toBeVisible()
    expect(h.devices[1].sent.filter((event) => event.type === 'response.create')).toHaveLength(1)
  })

  it('keeps both polling loops read-only, drains during finalization and hands off only canonical completed data', async () => {
    const h = harness()
    const view = await room()
    await click('Start interview')
    await answer(h)
    const reads = h.requests.filter((request) => request.method === 'GET').length
    const writes = h.requests.filter((request) => request.method === 'POST').length
    await tick()
    expect(h.requests.filter((request) => request.method === 'GET')).toHaveLength(reads + 2)
    expect(h.requests.filter((request) => request.method === 'POST')).toHaveLength(writes)
    h.server.interview.phase = 'finalizing'
    h.server.interview.flow_revision++
    await tick()
    expect(screen.getByText(/Finishing the transcript/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    expect(h.streams[0].track.enabled).toBe(false)
    expect(h.streams[0].track.stop).not.toHaveBeenCalled()
    expect(h.devices[0].channel.close).not.toHaveBeenCalled()
    h.server.interview.phase = 'completed'
    h.server.interview.flow_revision++
    h.server.interview.ended_at = new Date().toISOString()
    await tick()
    expect(h.streams[0].track.stop).toHaveBeenCalled()
    await click('View feedback')
    expect(view.props.onFeedback).toHaveBeenCalledExactlyOnceWith(h.server.interview)
    expect(h.posts('end')).toHaveLength(0)
    const count = h.requests.length
    await tick(4000)
    expect(h.requests).toHaveLength(count)
  })

  it('shows finishing immediately while the real engine waits for a late final transcript', async () => {
    const h = harness()
    h.server.endPhase = 'finalizing'
    const view = await room()
    await click('Start interview')
    await act(async () => h.devices[0].emit({ type: 'input_audio_buffer.speech_started', item_id: 'candidate-1' }))
    await click('End interview')
    await click('Finish interview')
    expect(screen.getByText(/Finishing the transcript/)).toBeVisible()
    expect(h.posts('end')).toHaveLength(0)
    expect(h.streams[0].track.enabled).toBe(false)
    await answer(h)
    await tick(100)
    expect(h.posts('end')).toHaveLength(1)
    expect(h.devices[0].channel.close).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    h.server.interview.phase = 'completed'
    h.server.interview.flow_revision++
    await tick()
    await click('View feedback')
    expect(view.props.onFeedback).toHaveBeenCalledExactlyOnceWith(h.server.interview)
    expect(h.server.interview.turns).toEqual([expect.objectContaining({
      text: 'I tested the Python API with my team.', transcript_status: 'final',
    })])
  })

  it('releases the finalizing controller after an end request fails so reconnect can recover controls', async () => {
    const h = harness()
    h.server.endUnavailable = true
    await room()
    await click('Start interview')
    await click('End interview')
    await click('Finish interview')
    expect(screen.getByRole('alert')).toHaveTextContent('could not be completed')
    expect(h.streams[0].track.stop).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Reconnect voice' })).toBeEnabled()
    h.server.endUnavailable = false
    await click('Reconnect voice')
    expect(h.streams[1].track.enabled).toBe(false)
    const voice = h.devices[1]
    const request = voice.sent.find(event => event.type === 'response.create')!.response as { metadata: unknown }
    await act(async () => {
      voice.emit({ type: 'response.created', response: { id: 'reconnected-question', metadata: request.metadata } })
      voice.emit({ type: 'response.done', response: { id: 'reconnected-question', status: 'completed', output: [] } })
      voice.emit({ type: 'output_audio_buffer.stopped', response_id: 'reconnected-question' })
    })
    expect(h.streams[1].track.enabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Skip question' })).toBeEnabled()
  })

  it('rejects a delayed UI read after the controller has reported canonical completion', async () => {
    const h = harness()
    await room()
    await click('Start interview')
    const stale = h.json(h.server.interview)
    const read = h.delayRead()
    h.server.interview.phase = 'completed'
    h.server.interview.flow_revision++
    await tick()
    expect(screen.getByRole('button', { name: 'View feedback' })).toBeEnabled()
    await act(async () => read.resolve(stale))
    expect(screen.getByRole('button', { name: 'View feedback' })).toBeEnabled()
    expect(screen.getByText('Microphone off', { exact: true })).toBeVisible()
  })

  it.each(['hidden', 'leave', 'pagehide', 'unmount'] as const)('releases hardware on %s without ending or reconnecting', async (action) => {
    const h = harness()
    const view = await room()
    await click('Start interview')
    if (action === 'hidden') view.rerender(<StrictMode><LiveInterviewStage {...view.props} visible={false} /></StrictMode>)
    else if (action === 'leave') await click('Leave interview room')
    else if (action === 'pagehide') act(() => window.dispatchEvent(new Event('pagehide')))
    else view.unmount()
    expect(h.streams[0].track.stop).toHaveBeenCalled()
    expect(h.devices[0].peer.close).toHaveBeenCalled()
    expect(h.devices[0].channel.close).toHaveBeenCalled()
    expect(h.devices[0].audio.pause).toHaveBeenCalled()
    expect(h.devices[0].audio.srcObject).toBeNull()
    expect(h.posts('end')).toHaveLength(0)
    await tick()
    expect(h.getUserMedia).toHaveBeenCalledTimes(1)
    if (action === 'unmount') expect(vi.getTimerCount()).toBe(0)
  })

  it('stops a late microphone grant after leaving and never starts the interview', async () => {
    const h = harness()
    const permission = deferred<ReturnType<typeof h.media>>()
    h.getUserMedia.mockReturnValueOnce(permission.promise)
    const view = await room()
    await click('Start interview')
    expect(screen.getByText('Microphone access requested · connecting')).toBeVisible()
    await click('Leave interview room')
    view.unmount()
    const lateStream = h.media()
    await act(async () => permission.resolve(lateStream))
    expect(lateStream.track.stop).toHaveBeenCalledTimes(1)
    expect(h.posts('start')).toHaveLength(0)
    expect(h.posts('realtime-token')).toHaveLength(0)
    expect(h.devices).toHaveLength(0)
  })
})
