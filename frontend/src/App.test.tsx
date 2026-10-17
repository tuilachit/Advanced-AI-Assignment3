import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App, { WorkflowApp } from './App'
import { api, ApiError } from './api'
import type { Session } from './types'

vi.mock('./components/PDFExportPanel', () => ({ default: () => null }))
afterEach(() => vi.restoreAllMocks())

const initialSession: Session = {
  session_id: 'session-1',
  state: 'collecting_profile',
  profile: { facts: [], revision: 0 },
  resume_entries: [],
  resume_entries_revision: 0,
  resume_entry_validation_issues: [],
  retrieval_results: [],
  selected_job_id: null,
  cv: null,
  validation_issues: [],
  validated_content_hash: null,
  trace: [],
}

const callbacks = {
  onSendMessage: vi.fn(),
  onConfirmProfile: vi.fn(),
  onProposeResumeEntries: vi.fn(),
  onEditResumeEntry: vi.fn(),
  onApproveResumeEntry: vi.fn(),
  onDeleteResumeEntry: vi.fn(),
  onRetrieveJobs: vi.fn(),
  onSelectJob: vi.fn(),
  onGenerateCV: vi.fn(),
  onSaveCV: vi.fn(),
  onValidateCV: vi.fn(),
  onRecordExport: vi.fn(),
}

const resumeReviewSession: Session = {
  ...initialSession,
  state: 'resume_entries_review',
  profile: { revision: 1, facts: [{
    fact_id: 'fact-project', field: 'project', value: 'Built a Python course-planning API.',
    status: 'confirmed', source: { source_type: 'user_message', reference: 'message-project' },
  }] },
  resume_entries_revision: 1,
  resume_entries: [{
    entry_id: 'resume-entry-1', kind: 'project', status: 'proposed', source_fact_ids: ['fact-project'],
    heading: { text: 'Course planning API', fact_ids: ['fact-project'] },
    organisation_or_context: { text: 'University project', fact_ids: ['fact-project'] },
    details: [{ label: 'Technology', value: { text: 'Python', fact_ids: ['fact-project'] } }],
    bullets: [{ text: 'Developed a course-planning API in Python.', fact_ids: ['fact-project'] }],
  }],
}

describe('resume entry review', () => {
  it('reconciles a whitespace-only successful save without clearing another entry draft', async () => {
    const entry = { ...resumeReviewSession.resume_entries[0], status: 'needs_review' as const }
    const session: Session = { ...resumeReviewSession, resume_entries: [
      entry, { ...entry, entry_id: 'resume-entry-2', heading: { ...entry.heading, text: 'Other project' } },
    ] }
    vi.spyOn(api, 'createSession').mockResolvedValue(session)
    vi.spyOn(api, 'updateResumeEntry').mockResolvedValue({ ...session, resume_entries_revision: 2 })
    render(<App />)
    const headings = await screen.findAllByLabelText('Heading')
    fireEvent.change(headings[0], { target: { value: '  Course planning API  ' } })
    fireEvent.change(headings[1], { target: { value: 'Unsaved other project' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save changes' })[0])
    await waitFor(() => expect(screen.getAllByLabelText('Heading')[0]).toHaveValue('Course planning API'))
    expect(screen.getAllByRole('button', { name: 'Save changes' })[0]).toBeDisabled()
    expect(screen.getAllByRole('button', { name: 'Approve entry' })[0]).toBeEnabled()
    expect(screen.getAllByLabelText('Heading')[1]).toHaveValue('Unsaved other project')
    expect(screen.getAllByRole('button', { name: 'Save changes' })[1]).toBeEnabled()
    expect(screen.getAllByRole('button', { name: 'Approve entry' })[1]).toBeDisabled()
  })

  it('retains an unsaved entry draft after a rejected save and unchanged session refresh', async () => {
    vi.spyOn(api, 'createSession').mockResolvedValue(resumeReviewSession)
    vi.spyOn(api, 'getSession').mockResolvedValue(resumeReviewSession)
    vi.spyOn(api, 'updateResumeEntry').mockRejectedValue(new ApiError({ error: {
      code: 'provider_unavailable', message: 'Please retry saving.', details: {},
    } }))
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Heading'), { target: { value: '  Course planning API  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please retry saving.')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled())
    expect(screen.getByLabelText('Heading')).toHaveValue('  Course planning API  ')
    expect(screen.getByRole('button', { name: 'Approve entry' })).toBeDisabled()
  })

  it('shows entry text, fact mappings, warnings and review history in the audit view', () => {
    const session: Session = { ...resumeReviewSession,
      resume_entry_validation_issues: [{ issue_id: 'entry-warning', entry_id: 'resume-entry-1',
        severity: 'warning', code: 'wording', message: 'Check the project wording.' }],
      trace: ['resume_entries_proposed', 'resume_entry_updated', 'resume_entry_approved'].map((event_type) => ({
        event_id: event_type, event_type, summary: `Recorded ${event_type}`,
        timestamp: '2026-09-09T00:00:00Z', details: { entry_id: 'resume-entry-1' },
      })),
    }
    render(<WorkflowApp session={session} messages={[]} busy={false} error={null} {...callbacks} />)
    fireEvent.click(screen.getByRole('button', { name: /Evidence/ }))
    const card = screen.getByRole('heading', { name: 'Resume entry map' }).closest('article')!
    expect(within(card).getByText('Course planning API')).toBeVisible()
    expect(within(card).getByText('University project')).toBeVisible()
    expect(within(card).getByText('Technology')).toBeVisible()
    expect(within(card).getByText('Python')).toBeVisible()
    expect(within(card).getByText('Developed a course-planning API in Python.')).toBeVisible()
    expect(card).toHaveTextContent('resume-entry-1')
    expect(card).toHaveTextContent('proposed')
    expect(card).toHaveTextContent('fact-project')
    expect(card).toHaveTextContent('Built a Python course-planning API.')
    expect(card).toHaveTextContent('Check the project wording.')
    for (const event of session.trace) expect(within(card).getByText(event.summary)).toBeVisible()
  })

  it('requires explicit entry approval before unlocking job matches', () => {
    const onApproveResumeEntry = vi.fn()
    render(<WorkflowApp session={resumeReviewSession} messages={[]} busy={false} error={null}
      {...callbacks} onApproveResumeEntry={onApproveResumeEntry} />)
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /CV studio/ })).toBeDisabled()
    expect(onApproveResumeEntry).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Approve entry' }))
    expect(onApproveResumeEntry).toHaveBeenCalledWith('resume-entry-1')
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
  })

  it('shows a conventional preview and readable sources without internal identifiers', () => {
    render(<WorkflowApp session={resumeReviewSession} messages={[]} busy={false} error={null} {...callbacks} />)
    expect(screen.getByRole('heading', { name: 'Course planning API' })).toBeVisible()
    expect(screen.getByText('University project')).toBeVisible()
    expect(screen.getByText('Developed a course-planning API in Python.', { selector: 'li' })).toBeVisible()
    expect(screen.getByText('Based on what you told us')).toBeVisible()
    expect(screen.getByText('Built a Python course-planning API.')).toBeVisible()
    expect(document.body.textContent).not.toMatch(/fact-project|message-project|resume-entry-1/)
  })

  it('sends only display edits and blocks approval until those edits are saved', () => {
    const onEditResumeEntry = vi.fn()
    render(<WorkflowApp session={resumeReviewSession} messages={[]} busy={false} error={null}
      {...callbacks} onEditResumeEntry={onEditResumeEntry} />)
    fireEvent.change(screen.getByLabelText('Heading'), { target: { value: 'Python API project' } })
    fireEvent.change(screen.getByLabelText('Organisation or context'), { target: { value: 'Course project' } })
    fireEvent.change(screen.getByLabelText('Technology'), { target: { value: 'Python API' } })
    fireEvent.change(screen.getByLabelText('Bullet 1'), { target: { value: 'Built a course-planning API.' } })
    expect(screen.getByRole('button', { name: 'Approve entry' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(onEditResumeEntry).toHaveBeenCalledWith('resume-entry-1', {
      heading: 'Python API project', organisation_or_context: 'Course project',
      details: ['Python API'], bullets: ['Built a course-planning API.'],
    })
  })

  it('shows recovery guidance for needs-review entries and disables all editing while busy', () => {
    const session: Session = { ...resumeReviewSession, resume_entries: [
      { ...resumeReviewSession.resume_entries[0], status: 'needs_review' },
    ] }
    render(<WorkflowApp session={session} messages={[]} busy={true} error={null} {...callbacks} />)
    expect(screen.getByText(/Review the wording against your confirmed facts/)).toBeVisible()
    for (const textbox of screen.getAllByRole('textbox')) expect(textbox).toBeDisabled()
    for (const name of ['Save changes', 'Approve entry', 'Remove entry']) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
  })

  it('allows removing an entry without sending source data', () => {
    const onDeleteResumeEntry = vi.fn()
    render(<WorkflowApp session={resumeReviewSession} messages={[]} busy={false} error={null}
      {...callbacks} onDeleteResumeEntry={onDeleteResumeEntry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove entry' }))
    expect(onDeleteResumeEntry).toHaveBeenCalledWith('resume-entry-1')
  })

  it('keeps an approved entry in Resume entries and unlocks job navigation only', () => {
    render(<WorkflowApp session={{ ...resumeReviewSession, state: 'resume_entries_approved',
      resume_entries: [{ ...resumeReviewSession.resume_entries[0], status: 'approved' }],
    }} messages={[]} busy={false} error={null} {...callbacks} />)
    expect(screen.getByRole('button', { name: /Resume entries/ })).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /CV studio/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Approve entry' })).toBeDisabled()
  })

  it('creates entries through the API without approving them automatically', async () => {
    const requests: Array<{ url: string; method?: string }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      requests.push({ url: String(input), method: init?.method })
      return new Response(JSON.stringify(requests.length === 1
        ? { ...initialSession, state: 'profile_confirmed' } : resumeReviewSession), { status: 200 })
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Create resume entries' }))
    expect(await screen.findByRole('heading', { name: 'Course planning API' })).toBeVisible()
    expect(requests).toEqual([
      { url: 'http://localhost:8000/api/sessions', method: 'POST' },
      { url: 'http://localhost:8000/api/sessions/session-1/resume-entries/propose', method: 'POST' },
    ])
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
  })

  it('refreshes the server session after a failed resume approval', async () => {
    const requests: Array<{ url: string; method?: string }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      requests.push({ url: String(input), method: init?.method })
      if (String(input).endsWith('/approve')) return new Response(JSON.stringify({
        error: { code: 'provider_unavailable', message: 'Please retry approval.', details: {} },
      }), { status: 503 })
      const result = requests.length === 1 ? resumeReviewSession : {
        ...resumeReviewSession, state: 'profile_review',
      }
      return new Response(JSON.stringify(result), { status: 200 })
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Approve entry' }))
    expect(await screen.findByRole('heading', { name: 'Build your evidence profile' })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('Please retry approval.')
    expect(requests.slice(1)).toEqual([
      { url: 'http://localhost:8000/api/sessions/session-1/resume-entries/resume-entry-1/approve', method: 'POST' },
      { url: 'http://localhost:8000/api/sessions/session-1', method: undefined },
    ])
  })

  it('saves text through the API, then explicitly approves and removes the saved entry', async () => {
    const requests: Array<{ url: string; method?: string; body?: unknown }> = []
    const editedEntry = { ...resumeReviewSession.resume_entries[0], status: 'needs_review' as const,
      heading: { text: 'Python API project', fact_ids: ['fact-project'] } }
    const edited: Session = { ...resumeReviewSession, resume_entries_revision: 2, resume_entries: [editedEntry] }
    const approved: Session = { ...edited, state: 'resume_entries_approved', resume_entries_revision: 3,
      resume_entries: [{ ...editedEntry, status: 'approved' }] }
    const responses: Session[] = [resumeReviewSession, edited, approved, {
      ...initialSession, state: 'resume_entries_review', profile: resumeReviewSession.profile,
      resume_entries_revision: 4,
    }]
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      requests.push({ url: String(input), method: init?.method,
        body: init?.body ? JSON.parse(String(init.body)) : undefined })
      return new Response(JSON.stringify(responses.shift()), { status: 200 })
    })
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Heading'), { target: { value: 'Python API project' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Needs review')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Approve entry' }))
    expect(await screen.findByText('Approved')).toBeVisible()
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove entry' }))
    expect(await screen.findByRole('button', { name: 'Create resume entries' })).toBeVisible()
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
    expect(requests.slice(1)).toEqual([
      { url: 'http://localhost:8000/api/sessions/session-1/resume-entries/resume-entry-1', method: 'PUT', body: {
        heading: 'Python API project', organisation_or_context: 'University project',
        details: ['Python'], bullets: ['Developed a course-planning API in Python.'],
      } },
      { url: 'http://localhost:8000/api/sessions/session-1/resume-entries/resume-entry-1/approve', method: 'POST', body: undefined },
      { url: 'http://localhost:8000/api/sessions/session-1/resume-entries/resume-entry-1', method: 'DELETE', body: undefined },
    ])
  })
})

describe('guided workflow', () => {
  it('renders and saves human-readable CV statements after an edit', async () => {
    const onSaveCV = vi.fn().mockResolvedValue(undefined)
    render(<WorkflowApp session={{ ...initialSession, state: 'cv_draft', profile: { revision: 1, facts: [{
      fact_id: 'project-1', field: 'project', value: 'Built a Python API', status: 'confirmed',
      source: { source_type: 'user_message', reference: 'message-1' },
    }] }, cv: {
      cv_id: 'cv-1', target_job_id: 'job-1', headline: 'Student', headline_fact_ids: [], claims: [],
      sections: [{ heading: 'Projects', claims: [{ claim_id: 'section-1',
        text: 'Built a Python API.', fact_ids: ['project-1'], verified: true }] }],
    } }} messages={[]} busy={false} error={null} {...callbacks} onSaveCV={onSaveCV} />)
    const claim = screen.getByLabelText('Projects statement 1')
    expect(screen.getByText('Supported by your confirmed profile: Built a Python API')).toBeVisible()
    fireEvent.change(claim, { target: { value: 'Built and tested a Python API.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(onSaveCV.mock.calls[0][0].sections[0].claims[0]).toEqual({
      claim_id: 'section-1', text: 'Built and tested a Python API.', fact_ids: ['project-1'], verified: false,
    })
  })

  it('does not describe draft profile evidence as confirmed', () => {
    render(<WorkflowApp session={{ ...initialSession, profile: { revision: 1, facts: [{
      fact_id: 'draft-1', field: 'skills', value: 'Python', status: 'draft',
      source: { source_type: 'user_message', reference: 'message-1' },
    }] } }} messages={[]} busy={false} error={null} {...callbacks} />)
    fireEvent.click(screen.getByRole('button', { name: /Evidence/ }))
    const card = screen.getByRole('heading', { name: 'Profile facts' }).closest('article')!
    expect(within(card).getByText(/Status: draft/)).toBeVisible()
  })

  it('reconciles a committed profile update after agent failure and recovers', async () => {
    const validated: Session = { ...initialSession, state: 'cv_validated',
      validated_content_hash: 'hash', cv: { cv_id: 'cv-1', target_job_id: 'job-1',
        headline: 'Stale headline', headline_fact_ids: [], claims: [], sections: [] } }
    const updated: Session = { ...initialSession, state: 'profile_review',
      profile: { revision: 2, facts: [{ fact_id: 'fact-new', field: 'project',
        value: 'New authoritative project', status: 'draft',
        source: { source_type: 'user_message', reference: 'message-2' } }] } }
    vi.spyOn(api, 'createSession').mockResolvedValue(validated)
    vi.spyOn(api, 'getSession').mockResolvedValue(updated)
    vi.spyOn(api, 'sendMessage')
      .mockRejectedValueOnce(new ApiError({ error: { code: 'provider_unavailable', message: 'Provider failed', details: {} } }))
      .mockResolvedValueOnce({ message: 'Recovered', observations: [], session: updated })
    await act(async () => { render(<App />) })
    fireEvent.click(await screen.findByRole('button', { name: /Profile/ }))
    fireEvent.change(screen.getByLabelText('Add or correct profile information'), { target: { value: 'New project' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add to profile' }))
    expect(await screen.findByText('New authoritative project')).toBeVisible()
    expect(screen.getByRole('button', { name: /CV studio/ })).toBeDisabled()
    expect(screen.queryByDisplayValue('Stale headline')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Add or correct profile information'), { target: { value: 'Continue' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add to profile' }))
    await waitFor(() => expect(screen.getByText('Recovered')).toBeVisible())
  })

  it('hides stale workflow if reconciliation fails and lets the user refresh it', async () => {
    vi.spyOn(api, 'createSession').mockResolvedValue({ ...initialSession, state: 'cv_validated',
      validated_content_hash: 'hash', cv: { cv_id: 'cv-1', target_job_id: 'job-1',
        headline: 'Old CV', headline_fact_ids: [], claims: [], sections: [] } })
    vi.spyOn(api, 'sendMessage').mockRejectedValue(new Error('Connection lost'))
    vi.spyOn(api, 'getSession').mockRejectedValueOnce(new Error('Refresh failed'))
      .mockResolvedValueOnce(initialSession)
    await act(async () => { render(<App />) })
    fireEvent.click(screen.getByRole('button', { name: /Profile/ }))
    fireEvent.change(screen.getByLabelText('Add or correct profile information'), { target: { value: 'Update' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add to profile' }))
    const refresh = await screen.findByRole('button', { name: 'Refresh session' })
    expect(screen.queryByRole('button', { name: /CV studio/ })).not.toBeInTheDocument()
    fireEvent.click(refresh)
    expect(await screen.findByRole('heading', { name: 'Build your evidence profile' })).toBeVisible()
    expect(screen.getByRole('button', { name: /CV studio/ })).toBeDisabled()
  })

  it('starts in Profile and keeps later workflow stages locked', () => {
    render(
      <WorkflowApp
        session={initialSession}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Build your evidence profile' })).toBeVisible()
    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /CV studio/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Evidence/ })).toBeEnabled()
  })

  it('opens resume entry creation after profile confirmation and keeps retrieval locked', () => {
    const confirmed: Session = {
      ...initialSession,
      state: 'profile_confirmed',
      profile: {
        revision: 1,
        facts: [
          {
            fact_id: 'fact-1',
            field: 'skills',
            value: 'Python and REST APIs',
            status: 'confirmed',
            source: { source_type: 'user_message', reference: 'message-1' },
          },
        ],
      },
    }
    render(
      <WorkflowApp
        session={confirmed}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    expect(screen.getByRole('button', { name: /Job matches/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Create resume entries' })).toBeEnabled()
  })

  it('keeps raw message references out of the profile confirmation view', () => {
    const review: Session = {
      ...initialSession,
      state: 'profile_review',
      profile: {
        revision: 1,
        facts: [{
          fact_id: 'fact-1',
          field: 'skills',
          value: 'Python and REST APIs',
          status: 'confirmed',
          source: { source_type: 'user_message', reference: 'message-1' },
        }],
      },
    }
    render(<WorkflowApp session={review} messages={[]} busy={false} error={null} {...callbacks} />)

    expect(screen.getByText('Source: Your message')).toBeVisible()
    expect(screen.queryByText('message-1')).not.toBeInTheDocument()
  })

  it('shows claim-to-fact evidence in the Evidence stage', () => {
    const withEvidence: Session = {
      ...initialSession,
      state: 'cv_draft',
      profile: {
        revision: 1,
        facts: [
          {
            fact_id: 'fact-1',
            field: 'project',
            value: 'Built a Python API',
            status: 'confirmed',
            source: { source_type: 'user_message', reference: 'message-1' },
          },
        ],
      },
      retrieval_results: [
        {
          document_id: 'job-1',
          title: 'Software Engineer',
          score: 0.792,
          score_breakdown: {
            semantic_score: 0.81,
            project_score: 0.9,
            skill_score: 0.74,
            target_role_score: 0.7,
            education_score: 0.65,
            experience_score: 0.55,
            evidence_score: 0.77,
            final_score: 0.792,
          },
          excerpt: 'Build reliable APIs.',
          match_reasons: ['project: python, api'],
          matched_skills: ['python'],
          missing_requirements: [],
          eligibility_notes: ['Verify eligibility.'],
        },
      ],
      selected_job_id: 'job-1',
      cv: {
        cv_id: 'cv-1',
        target_job_id: 'job-1',
        headline: 'Software Engineering Student',
        headline_fact_ids: [],
        claims: [
          {
            claim_id: 'claim-1',
            text: 'Built a Python API.',
            fact_ids: ['fact-1'],
            verified: false,
          },
        ],
        sections: [],
      },
    }
    render(
      <WorkflowApp
        session={withEvidence}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Evidence/ }))

    expect(screen.getByText('Built a Python API.')).toBeVisible()
    expect(screen.getByText('fact-1')).toBeVisible()
    expect(screen.getByText('Source: message-1')).toBeVisible()
  })

  it('separates matched skills from missing job requirements', () => {
    const retrieved = {
      ...initialSession,
      state: 'jobs_retrieved' as const,
      retrieval_results: [
        {
          document_id: 'job-1',
          title: 'AI Engineer',
          score: 0.79485,
          score_breakdown: {
            semantic_score: 0.78,
            project_score: 0.93,
            skill_score: 0.86,
            target_role_score: 0.72,
            education_score: 0.68,
            experience_score: 0.5,
            evidence_score: 0.813,
            final_score: 0.79485,
          },
          excerpt: 'Develop Python AI systems.',
          match_reasons: ['skills: python'],
          matched_skills: ['python'],
          missing_requirements: ['three years of production experience'],
          eligibility_notes: ['Verify the full job record.'],
        },
      ],
    }
    render(
      <WorkflowApp
        session={retrieved}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Job matches/ }))

    expect(screen.getByRole('heading', { name: 'Matched skills' })).toBeVisible()
    expect(screen.getByText('python')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Missing requirements' })).toBeVisible()
    expect(screen.getByText('three years of production experience')).toBeVisible()
  })

  it('shows relevance evidence while keeping requirements separate', () => {
    const retrieved: Session = {
      ...initialSession,
      state: 'jobs_retrieved',
      retrieval_results: [
        {
          document_id: 'job-1',
          title: 'AI Engineer',
          score: 0.79485,
          score_breakdown: {
            semantic_score: 0.78,
            project_score: 0.93,
            skill_score: 0.86,
            target_role_score: 0.72,
            education_score: 0.68,
            experience_score: 0.5,
            evidence_score: 0.813,
            final_score: 0.79485,
          },
          excerpt: 'Develop Python AI systems.',
          match_reasons: ['Built a Python retrieval project.'],
          matched_skills: ['python'],
          missing_requirements: ['three years of production experience'],
          eligibility_notes: ['Verify the full job record.'],
        },
      ],
    }
    render(
      <WorkflowApp
        session={retrieved}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Job matches/ }))

    expect(screen.getByText('Relevant to your confirmed profile')).toBeVisible()
    expect(screen.getByText('Why this appeared')).toBeVisible()
    expect(screen.queryByText('Relevance score')).not.toBeInTheDocument()
    expect(screen.queryByText('Project evidence')).not.toBeInTheDocument()
    expect(screen.queryByText('Source ID: job-1')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Missing requirements/ })).toBeVisible()
    expect(screen.queryByText(/eligibility probability/i)).not.toBeInTheDocument()
  })

  it('keeps export locked for a draft CV', () => {
    const draft: Session = {
      ...initialSession,
      state: 'cv_draft',
      selected_job_id: 'job-1',
      cv: {
        cv_id: 'cv-1',
        target_job_id: 'job-1',
        headline: 'Engineer',
        headline_fact_ids: [],
        claims: [],
        sections: [],
      },
    }
    render(
      <WorkflowApp
        session={draft}
        messages={[]}
        busy={false}
        error={null}
        {...callbacks}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /CV studio/ }))

    expect(screen.getByText('Validate this exact draft to unlock PDF export.')).toBeVisible()
    expect(screen.queryByRole('link', { name: /Download PDF/ })).not.toBeInTheDocument()
  })

  it('presents interpretive validation feedback as a review warning', () => {
    const validated: Session = {
      ...initialSession,
      state: 'cv_validated',
      validated_content_hash: 'validated-hash',
      cv: {
        cv_id: 'cv-1', target_job_id: 'job-1', headline: 'Computing student',
        headline_fact_ids: [], claims: [], sections: [],
      },
      validation_issues: [{
        issue_id: 'warning-1', claim_id: 'headline', severity: 'warning',
        code: 'interpretive_language',
        message: '“Backend-focused” is an interpretation of your REST API evidence.',
      }],
    }
    render(<WorkflowApp session={validated} messages={[]} busy={false} error={null} {...callbacks} />)

    fireEvent.click(screen.getByRole('button', { name: /CV studio/ }))

    expect(screen.getByText('Review wording')).toBeVisible()
    expect(screen.getByText(/Backend-focused/)).toBeVisible()
    expect(screen.queryByText('Change required')).not.toBeInTheDocument()
  })
})
