import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { preparedInterview } from '../../../test/interviewFixtures'
import type { Interview, TranscriptTurn } from '../../../types'
import { LiveInterviewStage } from './LiveInterviewStage'
import { initialLiveState, liveReducer } from './liveState'
import type { VoiceController, VoiceIntegration, VoiceNotification } from './voiceBridge'

function ready() { return preparedInterview({ request_id: 'test-live', job: { source: 'supplied_job', document_id: 'job-1' },
  consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true } }) }
function turn(patch: Partial<TranscriptTurn> = {}): TranscriptTurn {
  return { turn_id: 'answer-1', question_id: 'question-0', speaker: 'candidate', input_mode: 'live_voice',
    transcript_version: 1, transcript_status: 'partial', text: 'I built', delivery_status: 'not_applicable', timing: null, ...patch }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
function harness() {
  const holder = { interview: ready() }
  const listeners = new Set<(event: VoiceNotification) => void>()
  const emit = (event: VoiceNotification) => listeners.forEach((listener) => listener(event))
  const activate = () => {
    holder.interview = { ...holder.interview, phase: 'active', flow_revision: 1,
      started_at: new Date().toISOString(), current_question_id: 'question-0' }
    holder.interview.questions[0].status = 'issued'
    emit({ type: 'connection', status: 'connected' })
    emit({ type: 'question', question: holder.interview.questions[0], flow_revision: 1 })
  }
  const controller = {
    subscribe: vi.fn((listener: (event: VoiceNotification) => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }),
    connect: vi.fn(async () => { emit({ type: 'connection', status: 'connecting' }); activate() }),
    set_muted: vi.fn((muted: boolean) => emit({ type: 'activity', muted, candidate_speaking: false, interviewer_playing: false })),
    resume_audio: vi.fn(async () => {}), skip: vi.fn(async () => {}),
    finish: vi.fn(async () => {
      holder.interview = { ...holder.interview, phase: 'finalizing', flow_revision: holder.interview.flow_revision + 1 }
      return structuredClone(holder.interview)
    }),
    disconnect: vi.fn(() => emit({ type: 'connection', status: 'disconnected' })),
  } satisfies VoiceController
  const read = vi.fn(async () => structuredClone(holder.interview))
  const integration: VoiceIntegration = { createController: () => controller, readInterview: read }
  return { holder, controller, integration, emit, activate, read, listeners }
}
async function start() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start interview' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeEnabled())
}

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('live interview UI', () => {
  it('loads the real record but cannot start without a voice adapter', async () => {
    const readInterview = vi.fn(async () => ready())
    render(<LiveInterviewStage interview={ready()} integration={{ createController: () => null, readInterview }} onClose={vi.fn()} />)
    await waitFor(() => expect(readInterview).toHaveBeenCalledWith('setup-test-session', 'prepared-interview'))
    expect(screen.getByRole('button', { name: 'Start interview' })).toBeDisabled()
    expect(screen.getByText(/Live voice is not available/)).toBeVisible()
    expect(screen.getByRole('timer')).toHaveTextContent('10:00')
    expect(screen.queryByText(/Tell me about a project decision/)).not.toBeInTheDocument()
  })

  it('connects only on an explicit start and renders controller activity and mute controls', async () => {
    const h = harness()
    const { container } = render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    const orb = container.querySelector('.interviewer-visualizer')
    expect(orb).toHaveAttribute('aria-hidden', 'true')
    expect(orb).toHaveAttribute('data-state', 'ready')
    expect(h.controller.connect).not.toHaveBeenCalled()
    await start()
    expect(h.controller.connect).toHaveBeenCalledExactlyOnceWith('prepared-interview')
    expect(screen.getByText('Question 1 of 4')).toBeVisible()
    expect(screen.getByText('Tell me about a project decision 1.')).toBeVisible()
    act(() => h.emit({ type: 'activity', muted: false, candidate_speaking: false, interviewer_playing: true }))
    expect(screen.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
    expect(orb).toHaveAttribute('data-state', 'speaking')
    act(() => h.emit({ type: 'activity', muted: false, candidate_speaking: true, interviewer_playing: false }))
    expect(screen.getByRole('heading', { name: 'You have the floor' })).toBeVisible()
    expect(orb).toHaveAttribute('data-state', 'user-speaking')
    fireEvent.click(screen.getByRole('button', { name: 'Mute microphone' }))
    expect(h.controller.set_muted).toHaveBeenCalledWith(true)
    expect(orb).toHaveAttribute('data-state', 'muted')
    expect(screen.getByRole('button', { name: 'Unmute microphone' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Unmute microphone' }))
    expect(h.controller.set_muted).toHaveBeenCalledWith(false)
    expect(screen.getByRole('heading', { name: 'Listening' })).toBeVisible()
    expect(orb).toHaveAttribute('data-state', 'listening')
    fireEvent.click(screen.getByRole('button', { name: 'Disconnect voice' }))
    expect(screen.getByRole('heading', { name: 'Voice disconnected' })).toBeVisible()
    expect(orb).toHaveAttribute('data-state', 'disconnected')
    expect(h.controller.connect).toHaveBeenCalledTimes(1)
  })

  it('keeps final captions, labels missing/interrupted speech, and renders plain text', async () => {
    const h = harness()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await start()
    act(() => h.emit({ type: 'transcript', turn: turn() }))
    expect(screen.getByText('Live caption · may change')).toBeVisible()
    act(() => h.emit({ type: 'transcript', turn: turn({ text: '<script>not executable</script>', transcript_version: 2, transcript_status: 'final' }) }))
    act(() => h.emit({ type: 'transcript', turn: turn({ text: 'stale', transcript_version: 1 }) }))
    expect(screen.queryByText('stale')).not.toBeInTheDocument()
    expect(screen.getByText('<script>not executable</script>')).toBeVisible()
    expect(screen.getAllByText('Final transcript')).toHaveLength(1)
    act(() => h.emit({ type: 'transcript', turn: turn({ turn_id: 'missing', text: '', transcript_status: 'failed' }) }))
    expect(screen.getByText('This turn could not be transcribed.')).toBeVisible()
    act(() => h.emit({ type: 'transcript', turn: turn({ turn_id: 'interrupted', text: 'A question', speaker: 'interviewer',
      delivery_status: 'interrupted', transcript_status: 'final' }) }))
    expect(screen.getByText('Final transcript · interrupted')).toBeVisible()
  })

  it('shows microphone denial and reconnects only on request, preserving the transcript', async () => {
    const h = harness()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await start()
    act(() => {
      h.emit({ type: 'transcript', turn: turn({ text: 'My saved answer', transcript_status: 'final' }) })
      h.emit({ type: 'error', code: 'microphone_denied', message: 'Microphone access was denied. Allow it in your browser and retry.', retryable: true })
      h.emit({ type: 'connection', status: 'failed' })
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Microphone access was denied.')
    expect(screen.getByRole('button', { name: 'Skip question' })).toBeDisabled()
    expect(screen.getByText('Microphone off')).toBeVisible()
    expect(h.controller.connect).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Reconnect voice' }))
    await waitFor(() => expect(h.controller.connect).toHaveBeenCalledTimes(2))
    expect(screen.getByText('My saved answer')).toBeVisible()
  })

  it('delegates blocked playback recovery to the voice controller', async () => {
    const h = harness()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await start()
    act(() => h.emit({ type: 'error', code: 'audio_playback_blocked', message: 'Press Enable audio to listen.', retryable: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Enable audio' }))
    await waitFor(() => expect(h.controller.resume_audio).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('waits for server-issued questions on skip, and reports follow-ups without inflating main progress', async () => {
    const h = harness()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await start()
    fireEvent.click(screen.getByRole('button', { name: 'Skip question' }))
    await waitFor(() => expect(h.controller.skip).toHaveBeenCalledTimes(1))
    expect(screen.getByText('Question 1 of 4')).toBeVisible()
    act(() => h.emit({ type: 'question', flow_revision: 2, question: { ...h.holder.interview.questions[0],
      question_id: 'follow-up', parent_question_id: 'question-0', kind: 'follow_up', text: 'What did you learn?' } }))
    expect(screen.getByText('Question 1 of 4 · Follow-up')).toBeVisible()
    expect(screen.getByText('What did you learn?')).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '0')
  })

  it('requires finish confirmation and distinguishes finalizing from completed', async () => {
    const h = harness()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await start()
    fireEvent.click(screen.getByRole('button', { name: 'End interview' }))
    expect(h.controller.finish).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Keep practising' }))
    expect(h.controller.finish).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'End interview' }))
    fireEvent.click(screen.getByRole('button', { name: 'Finish interview' }))
    await screen.findByText(/Finishing the transcript/)
    expect(screen.queryByText('Interview complete')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /microphone$/i })).toBeDisabled()
    act(() => h.emit({ type: 'finished', interview: { ...h.holder.interview, phase: 'completed',
      flow_revision: 3, ended_at: new Date().toISOString(), end_reason: 'user_finished' } }))
    expect(screen.getByText('Interview complete')).toBeVisible()
    expect(screen.getByRole('button', { name: 'End interview' })).toBeDisabled()
    expect(screen.getByText(/Your available transcript remains here/)).toBeVisible()
  })

  it('uses wall-clock start time, keeps counting while muted, and never ends locally at zero', async () => {
    vi.useFakeTimers()
    const epoch = Date.parse('2026-10-23T01:00:00Z')
    vi.setSystemTime(epoch)
    const h = harness()
    h.activate()
    render(<LiveInterviewStage interview={h.holder.interview} integration={h.integration} onClose={vi.fn()} />)
    await act(async () => {})
    act(() => h.emit({ type: 'connection', status: 'connected' }))
    fireEvent.click(screen.getByRole('button', { name: 'Mute microphone' }))
    vi.setSystemTime(epoch + 120_000)
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(screen.getByRole('timer')).toHaveTextContent('07:59')
    vi.setSystemTime(epoch + 700_000)
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(screen.getByRole('timer')).toHaveTextContent('00:00')
    expect(screen.getByText(/Time limit reached/)).toBeVisible()
    expect(screen.queryByText('Interview complete')).not.toBeInTheDocument()
    expect(h.controller.finish).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Skip question' })).toBeDisabled()
  })

  it('disconnects on hidden navigation and unmount without finishing or automatically reconnecting', async () => {
    const h = harness()
    const props = { interview: ready(), integration: h.integration, onClose: vi.fn() }
    const view = render(<LiveInterviewStage {...props} />)
    await start()
    view.rerender(<LiveInterviewStage {...props} visible={false} />)
    expect(h.controller.disconnect).toHaveBeenCalledTimes(1)
    expect(h.controller.finish).not.toHaveBeenCalled()
    view.rerender(<LiveInterviewStage {...props} visible />)
    expect(h.controller.connect).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(h.controller.disconnect).toHaveBeenCalledTimes(2)
    expect(h.listeners.size).toBe(0)
  })

  it('cancels an in-flight connect on leaving and ignores its late rejection', async () => {
    const h = harness()
    let reject!: (reason: Error) => void
    h.controller.connect.mockImplementation(() => new Promise<void>((_, fail) => { reject = fail }))
    const props = { interview: ready(), integration: h.integration, onClose: vi.fn() }
    const view = render(<LiveInterviewStage {...props} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    expect(screen.getByRole('button', { name: 'Connecting…' })).toBeDisabled()
    view.rerender(<LiveInterviewStage {...props} visible={false} />)
    await act(async () => { reject(new Error('Connection cancelled')) })
    view.rerender(<LiveInterviewStage {...props} visible />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Disconnected', { exact: true })).toBeVisible()
  })

  it('requires attaching a fresh controller before ending an already active interview', async () => {
    const h = harness()
    h.activate()
    render(<LiveInterviewStage interview={h.holder.interview} integration={h.integration} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect voice' })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'End interview' })).toBeDisabled()
    expect(screen.getByText(/Reconnect voice to attach/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Reconnect voice' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'End interview' })).toBeEnabled())
    expect(h.controller.finish).not.toHaveBeenCalled()
  })

  it('shows stale API state and recovers with an explicit read retry', async () => {
    const h = harness()
    h.read.mockRejectedValueOnce(new Error('offline'))
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('progress may be out of date')
    expect(screen.getByRole('button', { name: 'Start interview' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry status check' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled()
  })

  it('does not let late snapshots roll back an issued question or a completed interview', () => {
    const initial = initialLiveState(ready())
    const issued = liveReducer(initial, { type: 'question', flow_revision: 4, question: initial.interview.questions[1] })
    expect(liveReducer(issued, { type: 'snapshot', interview: ready() }).interview.current_question_id).toBe('question-1')
    const finished = liveReducer(issued, { type: 'finished', interview: { ...issued.interview, phase: 'completed' } })
    expect(liveReducer(finished, { type: 'snapshot', interview: { ...issued.interview, phase: 'active' } }).interview.phase).toBe('completed')
  })

  it('hands off to feedback only after backend completion and releases the controller', async () => {
    const h = harness()
    const onFeedback = vi.fn()
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} onFeedback={onFeedback} />)
    await start()
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    act(() => h.emit({ type: 'finished', interview: { ...h.holder.interview, phase: 'finalizing', flow_revision: 2 } }))
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    const completed = { ...h.holder.interview, phase: 'completed' as const, flow_revision: 3, ended_at: new Date().toISOString() }
    act(() => h.emit({ type: 'finished', interview: completed }))
    fireEvent.click(screen.getByRole('button', { name: 'View feedback' }))
    expect(onFeedback).toHaveBeenCalledWith(expect.objectContaining({ phase: 'completed', interview_id: completed.interview_id }))
    expect(h.controller.disconnect).toHaveBeenCalled()
  })

  it('releases pending controls on pagehide and refreshes on pageshow without reconnecting', async () => {
    const h = harness()
    const connection = deferred<void>()
    h.controller.connect.mockReturnValueOnce(connection.promise)
    render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    expect(screen.getByText('Microphone access requested · connecting')).toBeVisible()
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(h.controller.disconnect).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled()
    const reads = h.read.mock.calls.length
    act(() => window.dispatchEvent(new Event('pageshow')))
    await waitFor(() => expect(h.read.mock.calls.length).toBeGreaterThan(reads))
    await act(async () => connection.reject(new Error('Cancelled permission request')))
    expect(h.controller.connect).toHaveBeenCalledTimes(1)
    expect(h.controller.finish).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not let an old connect rejection fail a replacement controller connection', async () => {
    const old = harness()
    const next = harness()
    const oldConnection = deferred<void>()
    const nextConnection = deferred<void>()
    old.controller.connect.mockReturnValueOnce(oldConnection.promise)
    next.controller.connect.mockReturnValueOnce(nextConnection.promise)
    const props = { interview: ready(), onClose: vi.fn() }
    const view = render(<LiveInterviewStage {...props} integration={old.integration} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    view.rerender(<LiveInterviewStage {...props} integration={next.integration} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start interview' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    await act(async () => oldConnection.reject(new Error('Old connection cancelled')))
    expect(screen.getByText('Connecting', { exact: true })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await act(async () => { next.activate(); nextConnection.resolve() })
    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeEnabled()
    expect(old.listeners.size).toBe(0)
  })

  it('requires a new attachment when the controller is replaced during an active interview', async () => {
    const old = harness()
    const next = harness()
    const props = { interview: ready(), onClose: vi.fn() }
    const view = render(<LiveInterviewStage {...props} integration={old.integration} />)
    await start()
    next.holder.interview = structuredClone(old.holder.interview)
    view.rerender(<LiveInterviewStage {...props} integration={next.integration} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect voice' })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'End interview' })).toBeDisabled()
    expect(next.controller.connect).not.toHaveBeenCalled()
    expect(old.controller.disconnect).toHaveBeenCalledTimes(1)
  })

  it('ignores an old finish result after replacing the controller', async () => {
    const old = harness()
    const next = harness()
    const finishing = deferred<Interview>()
    old.controller.finish.mockReturnValueOnce(finishing.promise)
    const props = { interview: ready(), onClose: vi.fn(), onFeedback: vi.fn() }
    const view = render(<LiveInterviewStage {...props} integration={old.integration} />)
    await start()
    fireEvent.click(screen.getByRole('button', { name: 'End interview' }))
    fireEvent.click(screen.getByRole('button', { name: 'Finish interview' }))
    next.holder.interview = structuredClone(old.holder.interview)
    view.rerender(<LiveInterviewStage {...props} integration={next.integration} />)
    await act(async () => finishing.resolve({ ...old.holder.interview, phase: 'completed', flow_revision: 3 }))
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    expect(screen.queryByText('Interview complete', { exact: true })).not.toBeInTheDocument()
  })

  it('recovers a controller API warning when a status read succeeds without clearing playback errors', async () => {
    vi.useFakeTimers()
    const h = harness()
    h.activate()
    render(<LiveInterviewStage interview={h.holder.interview} integration={h.integration} onClose={vi.fn()} />)
    await act(async () => {})
    act(() => {
      h.emit({ type: 'connection', status: 'connected' })
      h.emit({ type: 'error', code: 'api_unreachable', message: 'Check FastAPI before continuing.', retryable: true })
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Listening' })).toBeVisible()
    act(() => h.emit({ type: 'error', code: 'audio_playback_blocked', message: 'Enable playback.', retryable: true }))
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByRole('button', { name: 'Enable audio' })).toBeVisible()
  })

  it('keeps the voice controller connected while polling finalization, then hands off the canonical transcript', async () => {
    vi.useFakeTimers()
    const h = harness()
    h.activate()
    const onFeedback = vi.fn()
    render(<LiveInterviewStage interview={h.holder.interview} integration={h.integration} onClose={vi.fn()} onFeedback={onFeedback} />)
    await act(async () => {})
    act(() => {
      h.emit({ type: 'connection', status: 'connected' })
      h.emit({ type: 'transcript', turn: turn({ text: 'Unconfirmed live caption' }) })
    })
    h.holder.interview = { ...h.holder.interview, phase: 'finalizing', flow_revision: 2 }
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText(/Finishing the transcript/)).toBeVisible()
    expect(h.controller.disconnect).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'View feedback' })).not.toBeInTheDocument()
    const final = turn({ turn_id: 'saved-answer', text: 'Persisted final answer.', transcript_status: 'final' })
    h.holder.interview = { ...h.holder.interview, phase: 'completed', flow_revision: 3, transcript_revision: 4, turns: [final] }
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(h.controller.disconnect).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Unconfirmed live caption')).not.toBeInTheDocument()
    act(() => h.emit({ type: 'transcript', turn: turn({ text: 'Late caption after completion' }) }))
    fireEvent.click(screen.getByRole('button', { name: 'View feedback' }))
    expect(onFeedback).toHaveBeenCalledWith(h.holder.interview)
    expect(h.controller.finish).not.toHaveBeenCalled()
  })

  it('ignores late reads and unsubscribed notifications after unmount', async () => {
    const h = harness()
    const pendingRead = deferred<Interview>()
    h.read.mockReturnValueOnce(pendingRead.promise)
    const view = render(<LiveInterviewStage interview={ready()} integration={h.integration} onClose={vi.fn()} />)
    const staleListener = h.controller.subscribe.mock.calls[0][0]
    view.unmount()
    const disconnects = h.controller.disconnect.mock.calls.length
    await act(async () => {
      pendingRead.resolve({ ...ready(), phase: 'completed' })
      staleListener({ type: 'connection', status: 'connected' })
    })
    expect(h.listeners.size).toBe(0)
    expect(h.controller.disconnect).toHaveBeenCalledTimes(disconnects)
    expect(h.controller.connect).not.toHaveBeenCalled()
  })

  it('does not surface an earlier GET failure after a completion event in the same batch', async () => {
    const h = harness()
    h.activate()
    const pendingRead = deferred<Interview>()
    h.read.mockReturnValueOnce(pendingRead.promise)
    render(<LiveInterviewStage interview={h.holder.interview} integration={h.integration} onClose={vi.fn()} onFeedback={vi.fn()} />)
    await act(async () => {
      h.emit({ type: 'finished', interview: { ...h.holder.interview, phase: 'completed', flow_revision: 2 } })
      pendingRead.reject(new Error('Earlier status request failed'))
    })
    expect(screen.getByRole('button', { name: 'View feedback' })).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
