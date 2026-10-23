import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from '../../api'
import { interviewSession, preparedInterview } from '../../test/interviewFixtures'
import type { Interview } from '../../types'
import { InterviewSetupStage } from './InterviewSetupStage'

afterEach(() => vi.restoreAllMocks())

const callbacks = { onReviewProfile: vi.fn(), onReviewEntries: vi.fn(), onReviewJobs: vi.fn() }
function consent() {
  fireEvent.click(screen.getByRole('checkbox', { name: /send my audio/ }))
  fireEvent.click(screen.getByRole('checkbox', { name: /keep my transcript/ }))
}

describe('interview setup', () => {
  it('allows exploring setup before approval but blocks interview creation', () => {
    const session = { ...interviewSession(), state: 'profile_review' as const, resume_entries: [] }
    const create = vi.spyOn(api, 'createInterview')
    render(<InterviewSetupStage session={session} busy={false} {...callbacks} />)
    consent()
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
    expect(screen.getByText(/approve a resume entry before preparing/)).toBeVisible()
    expect(create).not.toHaveBeenCalled()
  })

  it('prefills the selected job and sends the validated CV with explicit consent', async () => {
    const create = vi.spyOn(api, 'createInterview').mockImplementation(async (_, body) => preparedInterview(body))
    render(<InterviewSetupStage session={interviewSession()} busy={false} {...callbacks} />)
    expect(screen.getByLabelText('Target job')).toHaveValue('job-1')
    expect(screen.getByRole('checkbox', { name: /Include my current validated CV/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /send my audio/ }))
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /keep my transcript/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    expect(await screen.findByText('Interview prepared')).toBeVisible()
    expect(create).toHaveBeenCalledWith('setup-test-session', {
      request_id: expect.any(String), cv_id: 'validated-cv',
      job: { source: 'supplied_job', document_id: 'job-1' },
      config: { interview_type: 'mixed', duration_minutes: 10, main_question_count: 4, max_follow_ups_per_question: 1, language: 'en' },
      consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true },
    })
    expect(screen.getByText(/timer has not started/)).toBeVisible()
    expect(screen.queryByText(/Tell me about a project decision/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Set up another interview' }))
    expect(screen.getByRole('checkbox', { name: /send my audio/ })).not.toBeChecked()
  })

  it('allows a pasted role without a CV and trims whitespace in the request', async () => {
    const session = { ...interviewSession(), state: 'resume_entries_approved' as const,
      cv: null, validated_content_hash: null, retrieval_results: [], selected_job_id: null }
    const create = vi.spyOn(api, 'createInterview').mockImplementation(async (_, body) => preparedInterview(body, session))
    render(<InterviewSetupStage session={session} busy={false} {...callbacks} />)
    expect(screen.getByRole('checkbox', { name: /Include my current validated CV/ })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Job title'), { target: { value: '  Developer  ' } })
    fireEvent.change(screen.getByLabelText('Job description'), { target: { value: '  Build reliable APIs.  ' } })
    fireEvent.change(screen.getByLabelText('Time limit'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Main questions'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Follow-ups per question'), { target: { value: '0' } })
    consent()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    await screen.findByText('Interview prepared')
    expect(create.mock.calls[0][1]).toMatchObject({
      cv_id: null, job: { source: 'pasted_job', title: 'Developer', description: 'Build reliable APIs.' },
      config: { duration_minutes: 5, main_question_count: 3, max_follow_ups_per_question: 0 },
    })
  })

  it('keeps whitespace-only and overlength descriptions from being submitted', () => {
    const create = vi.spyOn(api, 'createInterview')
    render(<InterviewSetupStage session={interviewSession()} busy={false} {...callbacks} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Paste a job description' }))
    fireEvent.change(screen.getByLabelText('Job title'), { target: { value: 'Developer' } })
    fireEvent.change(screen.getByLabelText('Job description'), { target: { value: '   ' } })
    consent()
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Job description'), { target: { value: 'x'.repeat(20_001) } })
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
    expect(create).not.toHaveBeenCalled()
  })

  it('locks controls and prevents duplicate requests while questions are prepared', async () => {
    let resolve!: (interview: Interview) => void
    const create = vi.spyOn(api, 'createInterview').mockReturnValue(new Promise((done) => { resolve = done }))
    render(<InterviewSetupStage session={interviewSession()} busy={false} {...callbacks} />)
    consent()
    const form = screen.getByRole('form', { name: 'Interview setup' })
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(create).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Preparing interview…' })).toBeDisabled()
    expect(screen.getByLabelText('Target job')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Review profile' })).toBeDisabled()
    await act(async () => resolve(preparedInterview(create.mock.calls[0][1])))
    expect(await screen.findByText('Interview prepared')).toBeVisible()
  })

  it('retries an unchanged failed request with the same ID, retaining the setup', async () => {
    const create = vi.spyOn(api, 'createInterview')
      .mockRejectedValueOnce(new TypeError('Network failure'))
      .mockImplementationOnce(async (_, body) => preparedInterview(body))
    render(<InterviewSetupStage session={interviewSession()} busy={false} {...callbacks} />)
    consent()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your setup is kept here')
    expect(screen.getByLabelText('Target job')).toHaveValue('job-1')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('Interview prepared')
    expect(create.mock.calls[0][1].request_id).toBe(create.mock.calls[1][1].request_id)
  })

  it('uses a new request ID when the user changes the failed request', async () => {
    const create = vi.spyOn(api, 'createInterview').mockRejectedValue(new ApiError({
      error: { code: 'provider_unavailable', message: 'Question planner is unavailable. Please retry.', details: {} },
    }))
    render(<InterviewSetupStage session={interviewSession()} busy={false} {...callbacks} />)
    consent()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    await screen.findByRole('alert')
    fireEvent.change(screen.getByLabelText('Interview focus'), { target: { value: 'technical' } })
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2))
    expect(create.mock.calls[0][1].request_id).not.toBe(create.mock.calls[1][1].request_id)
    await screen.findByRole('alert')
  })

  it('removes stale CV inclusion and consent when the confirmed context changes', () => {
    const session = interviewSession()
    const view = render(<InterviewSetupStage session={session} busy={false} {...callbacks} />)
    consent()
    view.rerender(<InterviewSetupStage session={{ ...session, state: 'profile_review',
      profile: { ...session.profile, revision: 2 }, cv: null, validated_content_hash: null,
      resume_entries: [] }} busy={false} {...callbacks} />)
    expect(screen.getByRole('checkbox', { name: /Include my current validated CV/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /send my audio/ })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
  })

  it('keeps a prepared interview tied to its original context after profile edits', async () => {
    vi.spyOn(api, 'createInterview').mockImplementation(async (_, body) => preparedInterview(body))
    const session = interviewSession()
    const view = render(<InterviewSetupStage session={session} busy={false} {...callbacks} />)
    consent()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare interview' }))
    await screen.findByText('Interview prepared')
    view.rerender(<InterviewSetupStage session={{ ...session, profile: { ...session.profile, revision: 2 } }} busy={false} {...callbacks} />)
    expect(screen.getByText(/keeps its original information/)).toBeVisible()
    expect(screen.getByText('Interview prepared')).toBeVisible()
  })
})
