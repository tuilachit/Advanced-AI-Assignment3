import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FeedbackStage } from './FeedbackStage'
import { InterviewFeedback } from './InterviewFeedback'
import { SpeakingMetrics } from './SpeakingMetrics'
import { createSampleFeedback } from './sampleFeedback'
import { evidenceTurn, type SampleFeedbackSource as FeedbackSource, type FeedbackView } from './feedbackView'

function readySource(report: FeedbackView): FeedbackSource {
  return { kind: 'sample', load: vi.fn(async () => structuredClone(report)) }
}
function openQuestion(text: string) {
  fireEvent.click(screen.getByRole('heading', { name: text }).closest('summary')!)
}

describe('feedback screen', () => {
  it('shows completion and per-criterion coaching without an invented aggregate score', async () => {
    const sample = createSampleFeedback()
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    expect(screen.getByText('Sample feedback · mock data')).toBeVisible()
    expect(screen.getByText('6 min 20 sec')).toBeVisible()
    expect(screen.getByText('2 of 3 asked')).toBeVisible()
    expect(screen.getByText('1 skipped · 1 not asked')).toBeVisible()
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    const firstQuestion = screen.getByRole('heading', { name: sample.interview.questions[0].text }).closest('details')!
    expect(within(firstQuestion).getByLabelText('Relevance: 3 of 4 — Clear and well supported')).toBeVisible()
    expect(within(firstQuestion).getByLabelText('STAR: 2 of 4 — Partially meets the criterion')).toBeVisible()
    expect(within(firstQuestion).getByText('Situation · Task · Action · Result')).toBeVisible()
    expect(screen.queryByText(/overall score|overall percentage/i)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Not asked in this interview' })).toBeVisible()
  })

  it('keeps genuine zero scores and zero measurements distinct from unavailable data', async () => {
    const sample = createSampleFeedback()
    sample.report.questions[0].criteria[0].rating = { kind: 'assessed', score: 0 }
    sample.report.questions[0].measures[1].measurement = { kind: 'available', value: 0, unit: 'count' }
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByLabelText('Relevance: 0 of 4 — Does not address the criterion')
    const metrics = screen.getAllByRole('region', { name: 'Speaking metrics for this answer' })[0]
    expect(within(within(metrics).getByRole('region', { name: 'Transcript fillers' })).getByText('0')).toBeVisible()
    const pauses = within(metrics).getByRole('region', { name: 'Pauses' })
    expect(within(pauses).getByText('Not available')).toBeVisible()
    expect(within(pauses).queryByText('0')).not.toBeInTheDocument()
  })

  it('applies STAR to the behavioural sample and marks technical STAR not applicable', async () => {
    const sample = createSampleFeedback()
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    openQuestion('How would you test an API before releasing it to users?')
    const question = screen.getByRole('heading', { name: 'How would you test an API before releasing it to users?' }).closest('details')!
    const star = within(question).getByRole('region', { name: 'STAR evaluation' })
    expect(within(star).getByText('Not applicable')).toBeVisible()
    expect(star.querySelector('.feedback-score')).toBeNull()
    expect(within(question).getByLabelText('Technical reasoning: 3 of 4 — Clear and well supported')).toBeVisible()
  })

  it('does not score failed transcription or display missing measurements as zero', async () => {
    const sample = createSampleFeedback('insufficient')
    const view = render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    expect(screen.getAllByText('Insufficient evidence')).toHaveLength(5)
    expect(screen.getAllByText('Not available')).toHaveLength(3)
    expect(view.container.querySelectorAll('.feedback-score, .feedback-metric-value')).toHaveLength(0)
    expect(screen.getByText('No submitted answer')).toBeVisible()
  })

  it('shows skipped questions as unassessed and excludes planned questions from reviews', async () => {
    const sample = createSampleFeedback()
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    openQuestion('Tell me about a time you helped your team resolve a disagreement.')
    const skipped = screen.getByRole('heading', { name: 'Tell me about a time you helped your team resolve a disagreement.' }).closest('details')!
    expect(within(skipped).getByText('Skipped')).toBeVisible()
    expect(within(skipped).getAllByText('Insufficient evidence')).toHaveLength(5)
    expect(skipped.querySelector('.feedback-score')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'How would you investigate a slow API response?' })).not.toBeInTheDocument()
  })

  it('links exact quotes to their full final answer and keeps the transcript plain text', async () => {
    const sample = createSampleFeedback()
    sample.interview.turns[0].text += ' <script>example only</script>'
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    fireEvent.click(screen.getAllByRole('button', { name: 'View full answer' })[0])
    const answer = screen.getByText(/<script>example only<\/script>/)
    expect(answer).toBeVisible()
    expect(answer.closest('li')).toHaveFocus()
    expect(answer.closest('li')?.querySelector('script')).toBeNull()
  })

  it('withholds a score whose quote is missing or belongs to another question', async () => {
    const sample = createSampleFeedback()
    const criterion = sample.report.questions[0].criteria[0]
    criterion.evidence = [{ turnId: 'sample-turn-3', excerpt: 'I would test valid requests' }]
    render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    const firstQuestion = screen.getByRole('heading', { name: sample.interview.questions[0].text }).closest('details')!
    const relevance = within(firstQuestion).getByRole('region', { name: 'Relevance evaluation' })
    expect(within(relevance).getByText('Evidence unavailable')).toBeVisible()
    expect(relevance.querySelector('.feedback-score')).toBeNull()
    expect(within(relevance).queryByRole('button', { name: 'View full answer' })).not.toBeInTheDocument()
  })

  it('shows an initial loading state, a safe error, and a working retry without duplicate loads', async () => {
    const sample = createSampleFeedback()
    let reject!: (reason: Error) => void
    const load = vi.fn<FeedbackSource['load']>().mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
      .mockResolvedValue(sample.report)
    render(<FeedbackStage interview={sample.interview} source={{ kind: 'sample', load }} onBack={vi.fn()} />)
    expect(screen.getByText('Loading sample feedback…')).toBeVisible()
    await act(async () => reject(new Error('internal secret should not render')))
    expect(screen.getByRole('alert')).toHaveTextContent('sample report could not be loaded')
    expect(screen.queryByText(/internal secret/)).not.toBeInTheDocument()
    const retry = screen.getByRole('button', { name: 'Retry feedback' })
    fireEvent.click(retry)
    fireEvent.click(retry)
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('aborts a pending report when the screen unmounts', async () => {
    const sample = createSampleFeedback()
    let signal: AbortSignal | undefined
    const load = vi.fn<FeedbackSource['load']>((_interview, requestSignal) => { signal = requestSignal; return new Promise(() => {}) })
    const view = render(<FeedbackStage interview={sample.interview} source={{ kind: 'sample', load }} onBack={vi.fn()} />)
    expect(signal?.aborted).toBe(false)
    view.unmount()
    expect(signal?.aborted).toBe(true)
  })

  it('rejects a stale report and ignores a late response from a previous source', async () => {
    const sample = createSampleFeedback()
    let resolve!: (report: FeedbackView) => void
    const stale: FeedbackSource = { kind: 'sample', load: () => new Promise((done) => { resolve = done }) }
    const view = render(<FeedbackStage interview={sample.interview} source={stale} onBack={vi.fn()} />)
    const mismatch = { ...sample.report, transcriptRevision: 99 }
    view.rerender(<FeedbackStage interview={sample.interview} source={readySource(mismatch)} onBack={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('does not match the current interview')
    await act(async () => resolve(sample.report))
    expect(screen.getByRole('alert')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Question-by-question feedback' })).not.toBeInTheDocument()
  })

  it('does not request feedback before completion or when the service is unavailable', () => {
    const sample = createSampleFeedback()
    const source = readySource(sample.report)
    const view = render(<FeedbackStage interview={{ ...sample.interview, phase: 'finalizing' }} source={source} onBack={vi.fn()} />)
    expect(screen.getByText('Feedback needs a completed interview')).toBeVisible()
    expect(source.load).not.toHaveBeenCalled()
    view.rerender(<FeedbackStage interview={sample.interview} source={null} onBack={vi.fn()} />)
    expect(screen.getByText('Feedback is not connected yet')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Retry feedback' })).not.toBeInTheDocument()
  })

  it('separates the real completion summary from the explicitly selected sample', async () => {
    const sample = createSampleFeedback()
    const real = { ...sample.interview, interview_id: 'actual-interview', job: { ...sample.interview.job, title: 'Your actual target role' } }
    render(<InterviewFeedback interview={real} source={null} onBack={vi.fn()} onSetup={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Your actual target role' })).toBeVisible()
    expect(screen.queryByText('Sample feedback · mock data')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View sample feedback' }))
    expect(screen.getByText('Sample feedback · mock data')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Your actual target role' })).not.toBeInTheDocument()
    await screen.findByRole('heading', { name: 'Question-by-question feedback' })
    fireEvent.click(screen.getByRole('button', { name: 'Back to your interview summary' }))
    expect(screen.getByRole('heading', { name: 'Your actual target role' })).toBeVisible()
    expect(real.interview_id).toBe('actual-interview')
  })

  it('shows an honest empty report when no questions were asked', async () => {
    const sample = createSampleFeedback('empty')
    const view = render(<FeedbackStage interview={sample.interview} source={readySource(sample.report)} onBack={vi.fn()} />)
    expect(await screen.findByText('No questions were available to review')).toBeVisible()
    expect(screen.getByText('0 of 0 asked')).toBeVisible()
    expect(view.container.querySelectorAll('.feedback-score')).toHaveLength(0)
  })

  it('keeps unavailable reasons and measurement methods visible without inventing values', () => {
    const sample = createSampleFeedback()
    render(<SpeakingMetrics measures={sample.report.questions[0].measures} />)
    const pauses = screen.getByRole('region', { name: 'Pauses' })
    expect(within(pauses).getByText(/Audio-analysis pause intervals/)).toBeVisible()
    fireEvent.click(within(pauses).getByText('Method & coverage'))
    expect(within(pauses).getByText(/not inferred from punctuation/)).toBeVisible()
  })

  it('grounds every assessed mock criterion in an exact final answer from that question', () => {
    const sample = createSampleFeedback()
    for (const question of sample.report.questions) {
      for (const criterion of question.criteria) {
        if (criterion.rating.kind !== 'assessed') continue
        expect(criterion.evidence.length).toBeGreaterThan(0)
        for (const reference of criterion.evidence) expect(evidenceTurn(sample.interview, question.questionId, reference)).toBeDefined()
      }
    }
  })
})
