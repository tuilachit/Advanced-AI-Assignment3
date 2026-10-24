import { StrictMode } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FeedbackReport, FeedbackResponse, Interview } from '../../../types'
import { feedbackFixture, feedbackResponse, unassessedFeedback } from '../../../test/feedbackFixtures'
import { InterviewFeedback } from './InterviewFeedback'
import { feedbackView } from './feedbackService'

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }) }
function open(interview: Interview, visible = true) {
  return <InterviewFeedback interview={interview} visible={visible} onBack={vi.fn()} onSetup={vi.fn()} />
}
function stubRead(body: FeedbackResponse) {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => response(body))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('real Feedback API integration', () => {
  it('only reads on mount, including StrictMode, and uses the session/interview endpoint without caching', async () => {
    const { interview } = feedbackFixture()
    interview.session_id = 'session/with space'
    interview.interview_id = 'interview/one'
    const fetch = stubRead(feedbackResponse('not_requested'))
    render(<StrictMode>{open(interview)}</StrictMode>)
    await screen.findByRole('button', { name: 'Generate feedback' })
    for (const [url, init] of fetch.mock.calls) {
      expect(url).toBe('http://localhost:8000/api/sessions/session%2Fwith%20space/interviews/interview%2Fone/feedback')
      expect(init?.method).toBeUndefined()
      expect(init?.cache).toBe('no-store')
      expect(init?.signal).toBeInstanceOf(AbortSignal)
    }
    expect(screen.queryByText('Sample feedback · mock data')).not.toBeInTheDocument()
  })

  it('generates once on explicit action, sends only the canonical revision and request ID, then polls to ready', async () => {
    const { interview, report } = feedbackFixture()
    let started = false
    let polls = 0
    const fetch = vi.fn<typeof globalThis.fetch>(async (_url, init) => {
      if (init?.method === 'POST') { started = true; return response({ feedback_status: 'generating' }, 202) }
      return response(!started ? feedbackResponse('not_requested') : ++polls === 1
        ? feedbackResponse('generating') : feedbackResponse('ready', report))
    })
    vi.stubGlobal('fetch', fetch)
    render(open(interview))
    const button = await screen.findByRole('button', { name: 'Generate feedback' })
    vi.useFakeTimers()
    await act(async () => { fireEvent.click(button); fireEvent.click(button) })
    expect(screen.getByText('Generating your feedback…')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Generate feedback' })).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(screen.getByText('Feedback ready')).toBeVisible()
    const writes = fetch.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(writes).toHaveLength(1)
    expect(JSON.parse(writes[0][1]!.body as string)).toEqual({ request_id: expect.any(String), expected_transcript_revision: 7 })
    const count = fetch.mock.calls.length
    await act(() => vi.advanceTimersByTimeAsync(6000))
    expect(fetch).toHaveBeenCalledTimes(count)
  })

  it('displays existing real criteria, exact evidence, suggestions, STAR and unavailable metrics without requesting generation', async () => {
    const { interview, report } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('ready', report))
    render(open(interview))
    await screen.findByText('Feedback ready')
    const first = screen.getByRole('heading', { name: 'Tell me about a team project.' }).closest('details')!
    expect(within(first).getByLabelText('Relevance: 3 of 4 — Clear and well supported')).toBeVisible()
    expect(screen.getByLabelText('Specificity: 0 of 4 — Does not address the criterion')).toBeVisible()
    expect(screen.getByLabelText('STAR: 2 of 4 — Partially meets the criterion')).toBeVisible()
    expect(screen.getByText('Explain your own responsibility in the team.')).toBeVisible()
    const metrics = screen.getAllByRole('region', { name: 'Speaking metrics for this answer' })[0]
    expect(within(within(metrics).getByRole('region', { name: 'Transcript fillers' })).getByText('0')).toBeVisible()
    expect(within(within(metrics).getByRole('region', { name: 'Speaking pace' })).getByText('No usable audio timing.')).toBeVisible()
    fireEvent.click(screen.getAllByRole('button', { name: 'View full answer' })[0])
    expect(screen.getByText(interview.turns[0].text).closest('li')).toHaveFocus()
    fireEvent.click(screen.getByRole('heading', { name: 'How would you test an API?' }).closest('summary')!)
    expect(screen.getByLabelText('Technical reasoning: 2 of 4 — Partially meets the criterion')).toBeVisible()
    expect(screen.queryByText(/overall score|overall percentage/i)).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps insufficient evidence and unavailable values unscored', async () => {
    const { interview } = feedbackFixture()
    stubRead(feedbackResponse('ready', unassessedFeedback(interview)))
    const view = render(open(interview))
    await screen.findByText('Feedback ready')
    expect(screen.getAllByText('Insufficient evidence')).toHaveLength(10)
    expect(screen.getAllByText('Not available')).toHaveLength(6)
    expect(view.container.querySelectorAll('.feedback-score, .feedback-metric-value')).toHaveLength(0)
  })

  it('retries a failed generation explicitly and follows GET even when POST reused a ready report', async () => {
    const { interview, report } = feedbackFixture()
    let retried = false
    const fetch = vi.fn<typeof globalThis.fetch>(async (_url, init) => {
      if (init?.method === 'POST') { retried = true; return response({ feedback_status: 'generating' }, 202) }
      return response(retried ? feedbackResponse('ready', report) : feedbackResponse('failed'))
    })
    vi.stubGlobal('fetch', fetch)
    render(open(interview))
    const retry = await screen.findByRole('button', { name: 'Retry generation' })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/Provider detail/)).not.toBeInTheDocument()
    fireEvent.click(retry)
    await screen.findByText('Feedback ready')
    expect(fetch.mock.calls.map(([, init]) => init?.method ?? 'GET')).toEqual(['GET', 'POST', 'GET'])
  })

  it('does not offer a generation retry for a non-retryable failed report', async () => {
    const { interview } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('failed', null, false))
    render(open(interview))
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /Retry/ })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('recovers from an uncertain POST through GET without silently rescheduling a failed evaluation', async () => {
    const { interview } = feedbackFixture()
    let writes = 0
    const bodies: unknown[] = []
    const fetch = vi.fn<typeof globalThis.fetch>(async (_url, init) => {
      if (init?.method === 'POST') { bodies.push(JSON.parse(init.body as string)); writes++; throw new TypeError('Private network detail') }
      return response(feedbackResponse(writes ? 'failed' : 'not_requested'))
    })
    vi.stubGlobal('fetch', fetch)
    render(open(interview))
    fireEvent.click(await screen.findByRole('button', { name: 'Generate feedback' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry feedback' }))
    const retry = await screen.findByRole('button', { name: 'Retry generation' })
    expect(writes).toBe(1)
    fireEvent.click(retry)
    await screen.findByRole('button', { name: 'Retry feedback' })
    expect(writes).toBe(2)
    expect(bodies[1]).toEqual(bodies[0])
    expect(screen.queryByText(/Private network detail/)).not.toBeInTheDocument()
  })

  it('recovers a failed GET with a read-only retry', async () => {
    const { interview, report } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('ready', report))
    fetch.mockRejectedValueOnce(new TypeError('Offline'))
    render(open(interview))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry feedback' }))
    await screen.findByText('Feedback ready')
    expect(fetch.mock.calls.every(([, init]) => !init?.method)).toBe(true)
  })

  it.each(['transcript_revision_conflict', 'feedback_snapshot_conflict', 'invalid_interview_phase'])('requires a refreshed interview after %s', async (code) => {
    const { interview } = feedbackFixture()
    const fetch = vi.fn<typeof globalThis.fetch>(async (_url, init) => init?.method === 'POST'
      ? response({ error: { code, message: 'Internal detail', details: {} } }, 409) : response(feedbackResponse('not_requested')))
    vi.stubGlobal('fetch', fetch)
    render(open(interview))
    fireEvent.click(await screen.findByRole('button', { name: 'Generate feedback' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Return to the interview to reload')
    expect(screen.queryByRole('button', { name: /Retry|Generate/ })).not.toBeInTheDocument()
  })

  it.each(['interview_id', 'context_hash', 'transcript_revision'] as const)('withholds a report with a different %s', async (field) => {
    const { interview, report } = feedbackFixture()
    const mismatch: FeedbackReport = { ...report, [field]: field === 'transcript_revision' ? 99 : 'other-interview' }
    stubRead(feedbackResponse('ready', mismatch))
    const view = render(open(interview))
    expect(await screen.findByRole('alert')).toHaveTextContent('does not match the current interview')
    expect(view.container.querySelectorAll('.feedback-score')).toHaveLength(0)
  })

  it.each(['active', 'finalizing', 'cancelled'] as const)('makes no feedback requests while the interview is %s', (phase) => {
    const { interview } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('not_requested'))
    render(open({ ...interview, phase }))
    expect(screen.getByText('Feedback needs a completed interview')).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['session_id', 'interview_id', 'context_hash', 'transcript_revision'] as const)('aborts and ignores late responses when %s changes', async (field) => {
    const { interview, report } = feedbackFixture()
    let resolve!: (response: Response) => void
    const fetch = stubRead(feedbackResponse('not_requested'))
    fetch.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const view = render(open(interview))
    const signal = fetch.mock.calls[0][1]?.signal
    view.rerender(open({ ...interview, [field]: field === 'transcript_revision' ? 8 : 'changed' }))
    await screen.findByRole('button', { name: 'Generate feedback' })
    expect(signal?.aborted).toBe(true)
    await act(async () => resolve(response(feedbackResponse('ready', report))))
    expect(screen.queryByText('Feedback ready')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate feedback' })).toBeVisible()
  })

  it('cancels serial polling when hidden or unmounted and resumes with a read when visible again', async () => {
    const { interview } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('generating'))
    vi.useFakeTimers()
    const view = render(open(interview))
    await act(async () => {})
    expect(screen.getByText('Generating your feedback…')).toBeVisible()
    view.rerender(open(interview, false))
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true)
    await act(() => vi.advanceTimersByTimeAsync(6000))
    expect(fetch).toHaveBeenCalledTimes(1)
    view.rerender(open(interview))
    await act(async () => {})
    expect(fetch).toHaveBeenCalledTimes(2)
    view.unmount()
    await act(() => vi.advanceTimersByTimeAsync(6000))
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not start a second poll while the previous response is pending', async () => {
    const { interview } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('generating'))
    fetch.mockImplementationOnce(() => new Promise(() => {}))
    vi.useFakeTimers()
    const view = render(open(interview))
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(fetch).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })

  it('aborts an in-flight generation on leaving and ignores its late acknowledgement', async () => {
    const { interview } = feedbackFixture()
    let resolve!: (response: Response) => void
    const fetch = stubRead(feedbackResponse('not_requested'))
    fetch.mockImplementation(async (_url, init) => init?.method === 'POST'
      ? new Promise((done) => { resolve = done }) : response(feedbackResponse('not_requested')))
    const view = render(open(interview))
    fireEvent.click(await screen.findByRole('button', { name: 'Generate feedback' }))
    const signal = fetch.mock.calls[1][1]?.signal
    view.unmount()
    expect(signal?.aborted).toBe(true)
    await act(async () => resolve(response({ feedback_status: 'generating' }, 202)))
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows expired interview recovery without an endless retry action', async () => {
    const { interview } = feedbackFixture()
    const fetch = stubRead(feedbackResponse('not_requested'))
    fetch.mockResolvedValueOnce(response({ error: { code: 'interview_not_found', message: 'Missing', details: {} } }, 404))
    render(open(interview))
    expect(await screen.findByRole('alert')).toHaveTextContent('Return to setup to prepare another interview')
    expect(screen.queryByRole('button', { name: /Retry|Generate/ })).not.toBeInTheDocument()
  })

  it('rejects malformed assessed values without converting them to zero', () => {
    const { report } = feedbackFixture()
    report.question_feedback[0].criteria[0].score = null
    expect(() => feedbackView(report)).toThrow('Invalid criterion score')
    report.question_feedback[0].criteria[0].score = 3
    report.question_feedback[0].speaking_metrics[1].value = null
    expect(() => feedbackView(report)).toThrow('Invalid speaking measurement')
  })
})
