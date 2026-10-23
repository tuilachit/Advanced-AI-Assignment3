import { expect, test, type Page, type Route } from '@playwright/test'

import type { CVDocument, ResumeEntry, ResumeEntryEdit, Session } from '../src/types'

const profileFacts = [
  {
    fact_id: 'fact-name',
    field: 'name',
    value: 'Maya Chen',
    status: 'draft' as const,
    source: { source_type: 'user_message' as const, reference: 'message-1' },
  },
  {
    fact_id: 'fact-study',
    field: 'education',
    value: 'Third-year Computing Science student at UTS',
    status: 'draft' as const,
    source: { source_type: 'user_message' as const, reference: 'message-1' },
  },
  {
    fact_id: 'fact-goal',
    field: 'target_role',
    value: 'Graduate AI Engineer',
    status: 'draft' as const,
    source: { source_type: 'user_message' as const, reference: 'message-1' },
  },
  {
    fact_id: 'fact-skills', field: 'skills', value: 'Python and applied AI', status: 'draft' as const,
    source: { source_type: 'user_message' as const, reference: 'message-1' },
  },
  {
    fact_id: 'fact-project', field: 'project', value: 'Built and tested a Python course-planning API.', status: 'draft' as const,
    source: { source_type: 'user_message' as const, reference: 'message-1' },
  },
]

const cv: CVDocument = {
  cv_id: 'cv-1',
  target_job_id: 'graduate_ai_engineer',
  headline: 'Course-planning API project | Python',
  headline_fact_ids: ['fact-project'],
  claims: [
    {
      claim_id: 'claim-1',
      text: 'Built and tested a Python course-planning API.',
      fact_ids: ['fact-project'],
      verified: false,
    },
  ],
  sections: [{ heading: 'Technical skills', claims: [{ claim_id: 'claim-skills',
    text: 'Python', fact_ids: ['fact-project'], verified: false }] }],
}

function initialSession(id = 'session-00000001'): Session {
  return {
    session_id: id,
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
    trace: [
      {
        event_id: 'trace-1',
        timestamp: '2026-09-06T00:00:00Z',
        event_type: 'session_created',
        summary: 'Temporary session created.',
        details: {},
      },
    ],
  }
}

async function fulfill(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    json,
    headers: { 'access-control-allow-origin': route.request().headers().origin ?? '*' },
  })
}

async function installSuccessfulApi(
  page: Page,
  sessionId = 'session-00000001',
  facts: Session['profile']['facts'] = profileFacts,
  revisedFacts?: Session['profile']['facts'],
  failAfterRevision = false,
) {
  let session = initialSession(sessionId)
  let cvCount = 0
  const resetDownstream = () => {
    session.retrieval_results = []
    session.selected_job_id = null
    session.cv = null
    session.validation_issues = []
    session.validated_content_hash = null
  }
  const reconcileEntries = () => {
    session.state = session.resume_entries.some((entry) => entry.status === 'approved' && entry.kind !== 'skills')
      ? 'resume_entries_approved' : 'resume_entries_review'
  }
  const recordEntryEvent = (event_type: string, summary: string, entryId?: string) => {
    session.trace.push({ event_id: `trace-${session.trace.length + 1}`, event_type, summary,
      timestamp: '2026-09-09T00:01:00Z', details: entryId ? { entry_id: entryId } : {} })
  }

  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': request.headers().origin ?? '*',
          'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
          'access-control-allow-headers': 'content-type',
        },
      })
      return
    }

    const path = new URL(request.url()).pathname
    if (path === '/api/sessions' && request.method() === 'POST') {
      await fulfill(route, session, 201)
      return
    }
    const base = `/api/sessions/${sessionId}`
    if (path === base && request.method() === 'GET') {
      await fulfill(route, session)
      return
    }
    if (path === `${base}/messages` && request.method() === 'POST') {
      const profileRevision = session.profile.revision + 1
      const resetsDownstream = Boolean(revisedFacts && session.profile.revision > 0)
      const nextFacts = resetsDownstream ? revisedFacts! : facts
      const changedIds = nextFacts.filter((fact) => session.profile.facts.some(
        (previous) => previous.fact_id === fact.fact_id && previous.value !== fact.value,
      )).map((fact) => fact.fact_id)
      const staleEntries = session.resume_entries.filter((entry) => entry.status !== 'needs_review'
        && entry.source_fact_ids.some((id) => changedIds.includes(id)))
      resetDownstream()
      session = {
        ...session,
        state: 'profile_review',
        profile: { facts: nextFacts.map((fact) => ({ ...fact, status: 'draft' })), revision: profileRevision },
        resume_entries: session.resume_entries.map((entry) => staleEntries.includes(entry)
          ? { ...entry, status: 'needs_review' } : entry),
        resume_entries_revision: session.resume_entries_revision + Number(staleEntries.length > 0),
      }
      if (resetsDownstream && failAfterRevision) {
        failAfterRevision = false
        await fulfill(route, { error: { code: 'provider_unavailable',
          message: 'Provider failed after saving your profile.', details: {} } }, 503)
        return
      }
      await fulfill(route, {
        message: 'I captured your draft facts. Please review and confirm them.',
        observations: [],
        session,
      })
      return
    }
    if (path === `${base}/profile/confirm` && request.method() === 'POST') {
      session = {
        ...session,
        state: 'profile_confirmed',
        profile: {
          ...session.profile,
          facts: session.profile.facts.map((fact) => ({ ...fact, status: 'confirmed' as const })),
        },
      }
      if (session.resume_entries.length) reconcileEntries()
      await fulfill(route, session)
      return
    }
    if (path === `${base}/resume-entries/propose` && request.method() === 'POST') {
      if (!session.profile.facts.length || session.profile.facts.some((fact) => fact.status !== 'confirmed')) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Confirm the profile first.', details: {} } }, 409)
        return
      }
      const entry: ResumeEntry = {
        entry_id: `entry-${sessionId}`, kind: 'project', status: 'proposed', source_fact_ids: ['fact-project'],
        heading: { text: 'Course planning API', fact_ids: ['fact-project'] },
        organisation_or_context: null,
        details: [{ label: 'Technology', value: { text: 'Python', fact_ids: ['fact-project'] } }],
        bullets: [{ text: session.profile.facts.find((fact) => fact.fact_id === 'fact-project')!.value,
          fact_ids: ['fact-project'] }],
      }
      resetDownstream()
      session.resume_entries = [entry]
      session.resume_entries_revision += 1
      session.resume_entry_validation_issues = []
      session.state = 'resume_entries_review'
      recordEntryEvent('resume_entries_proposed', 'Proposed 1 resume entry.')
      await fulfill(route, session)
      return
    }
    const entry = session.resume_entries.find((candidate) => path === `${base}/resume-entries/${candidate.entry_id}`
      || path === `${base}/resume-entries/${candidate.entry_id}/approve`)
    if (entry && path.endsWith('/approve') && request.method() === 'POST') {
      if (entry.status === 'approved' || entry.source_fact_ids.some((id) => !session.profile.facts.some(
        (fact) => fact.fact_id === id && fact.status === 'confirmed',
      ))) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Confirm the entry sources before approval.', details: {} } }, 409)
        return
      }
      entry.status = 'approved'
      session.resume_entries_revision += 1
      session.resume_entry_validation_issues = []
      reconcileEntries()
      recordEntryEvent('resume_entry_approved', 'User approved a resume entry.', entry.entry_id)
      await fulfill(route, session)
      return
    }
    if (entry && path === `${base}/resume-entries/${entry.entry_id}` && request.method() === 'PUT') {
      const edit = request.postDataJSON() as ResumeEntryEdit
      const texts = [edit.heading, ...(edit.details ?? []), ...(edit.bullets ?? [])]
      if (Object.keys(edit).some((key) => !['heading', 'organisation_or_context', 'details', 'bullets'].includes(key))
        || edit.details?.length !== entry.details.length || edit.bullets?.length !== entry.bullets.length
        || (edit.organisation_or_context == null) !== (entry.organisation_or_context === null)
        || texts.some((text) => !text.trim())) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Preserve entry structure and nonempty display text.', details: {} } }, 409)
        return
      }
      entry.heading.text = edit.heading.trim()
      if (entry.organisation_or_context) entry.organisation_or_context.text = edit.organisation_or_context!.trim()
      entry.details.forEach((detail, index) => { detail.value.text = edit.details![index].trim() })
      entry.bullets.forEach((bullet, index) => { bullet.text = edit.bullets![index].trim() })
      entry.status = 'needs_review'
      session.resume_entries_revision += 1
      session.resume_entry_validation_issues = []
      resetDownstream()
      reconcileEntries()
      recordEntryEvent('resume_entry_updated', 'Updated a resume entry’s display text.', entry.entry_id)
      await fulfill(route, session)
      return
    }
    if (entry && path === `${base}/resume-entries/${entry.entry_id}` && request.method() === 'DELETE') {
      session.resume_entries = session.resume_entries.filter((candidate) => candidate !== entry)
      session.resume_entries_revision += 1
      session.resume_entry_validation_issues = session.resume_entry_validation_issues.filter((issue) => issue.entry_id !== entry.entry_id)
      resetDownstream()
      reconcileEntries()
      recordEntryEvent('resume_entry_removed', 'Removed a resume entry.', entry.entry_id)
      await fulfill(route, session)
      return
    }
    if (path === `${base}/jobs/retrieve` && request.method() === 'POST') {
      if (!session.resume_entries.some((entry) => entry.status === 'approved' && entry.kind !== 'skills')
        || session.profile.facts.some((fact) => fact.status !== 'confirmed')) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Approve a substantive resume entry before retrieving jobs.', details: {} } }, 409)
        return
      }
      resetDownstream()
      session = {
        ...session,
        state: 'jobs_retrieved',
        retrieval_results: [
          {
            document_id: 'graduate_ai_engineer',
            title: 'Graduate AI Engineer',
            score: 0.8854,
            score_breakdown: {
              semantic_score: 0.88,
              project_score: 1,
              skill_score: 0.86,
              target_role_score: 0.9,
              education_score: 0.84,
              experience_score: 0.58,
              evidence_score: 0.892,
              final_score: 0.8854,
            },
            excerpt: 'Develop and evaluate machine-learning models and AI agents.',
            match_reasons: ['Project evidence includes Python and applied AI.'],
            matched_skills: ['python'],
            missing_requirements: ['professional machine-learning experience'],
            eligibility_notes: ['Verify every requirement before applying.'],
          },
          {
            document_id: 'rag_agent_engineer',
            title: 'AI Engineer',
            score: 0.7655,
            score_breakdown: {
              semantic_score: 0.86,
              project_score: 0.82,
              skill_score: 0.42,
              target_role_score: 0.78,
              education_score: 0.7,
              experience_score: 0.3,
              evidence_score: 0.65,
              final_score: 0.7655,
            },
            excerpt: 'Design and optimise RAG pipelines and AI-agent workflows.',
            match_reasons: ['The profile mentions applied AI.'],
            matched_skills: [],
            missing_requirements: ['three years of research or engineering experience'],
            eligibility_notes: ['The role asks for experience not yet established.'],
          },
          {
            document_id: 'recommendation_systems_ml_engineer',
            title: 'Machine Learning Engineer',
            score: 0.705625,
            score_breakdown: {
              semantic_score: 0.79,
              project_score: 0.68,
              skill_score: 0.45,
              target_role_score: 0.72,
              education_score: 0.62,
              experience_score: 0.48,
              evidence_score: 0.6025,
              final_score: 0.705625,
            },
            excerpt: 'Implement, test and optimise machine-learning models.',
            match_reasons: ['Testing experience contributed to the match.'],
            matched_skills: [],
            missing_requirements: [],
            eligibility_notes: ['Verify every requirement before applying.'],
          },
        ],
      }
      await fulfill(route, session)
      return
    }
    const selectedJob = session.retrieval_results.find((job) => path === `${base}/jobs/${job.document_id}/select`)
    if (selectedJob && request.method() === 'POST') {
      session = { ...session, state: 'job_selected', selected_job_id: selectedJob.document_id,
        cv: null, validation_issues: [], validated_content_hash: null }
      await fulfill(route, session)
      return
    }
    if (path === `${base}/cvs` && request.method() === 'POST') {
      if (!session.selected_job_id) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Select a job first.', details: {} } }, 409)
        return
      }
      const generated = { ...cv, cv_id: `cv-${++cvCount}`, target_job_id: session.selected_job_id }
      session = {
        ...session,
        state: 'cv_draft',
        cv: generated,
        validation_issues: [],
        validated_content_hash: null,
        trace: [
          ...session.trace,
          {
            event_id: `trace-cv-generated-${generated.cv_id}`,
            timestamp: '2026-09-06T00:01:00Z',
            event_type: 'cv_generated',
            summary: 'CV draft generated for the selected job.',
            details: { cv_id: generated.cv_id, target_job_id: generated.target_job_id },
          },
        ],
      }
      await fulfill(route, { cv: generated, session }, 201)
      return
    }
    if (session.cv && path === `${base}/cvs/${session.cv.cv_id}/validate` && request.method() === 'POST') {
      session = {
        ...session,
        state: 'cv_validated',
        cv: {
          ...(session.cv ?? cv),
          claims: (session.cv ?? cv).claims.map((claim) => ({ ...claim, verified: true })),
          sections: (session.cv ?? cv).sections.map((section) => ({ ...section,
            claims: section.claims.map((claim) => ({ ...claim, verified: true })) })),
        },
        validated_content_hash: 'validated-hash',
        validation_issues: [],
      }
      await fulfill(route, session)
      return
    }
    if (session.cv && path === `${base}/cvs/${session.cv.cv_id}` && request.method() === 'PUT') {
      const edited = request.postDataJSON() as CVDocument
      session = {
        ...session,
        state: 'cv_draft',
        cv: { ...edited,
          claims: edited.claims.map((claim) => ({ ...claim, verified: false })),
          sections: edited.sections.map((section) => ({ ...section,
            claims: section.claims.map((claim) => ({ ...claim, verified: false })) })),
        },
        validated_content_hash: null,
      }
      await fulfill(route, session)
      return
    }
    if (session.cv && path === `${base}/cvs/${session.cv.cv_id}/export` && request.method() === 'POST') {
      if (!session.validated_content_hash || !['cv_validated', 'pdf_exported'].includes(session.state)) {
        await fulfill(route, { error: { code: 'invalid_transition', message: 'Validate the current CV before export.', details: {} } }, 409)
        return
      }
      session = {
        ...session,
        state: 'pdf_exported',
        trace: [
          ...session.trace,
          {
            event_id: `trace-pdf-exported-${session.trace.length + 1}`,
            timestamp: '2026-09-06T00:02:00Z',
            event_type: 'pdf_exported',
            summary: 'User exported the locally rendered PDF.',
            details: { cv_id: session.cv.cv_id },
          },
        ],
      }
      await fulfill(route, session)
      return
    }
    await fulfill(route, { error: { code: 'unexpected_route', message: path, details: {} } }, 500)
  })
}

async function checkResponsiveLayout(page: Page, stage: string) {
  const originalViewport = page.viewportSize()
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(page.locator('.stage-button')).toHaveCount(6)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (stage !== 'evidence') await expect(page.locator('body')).not.toContainText(/fact-project|message-1|entry-session|graduate_ai_engineer|session-00000001/)
    if (stage === 'cv' && width === 375) {
      const headline = page.getByLabel('Professional headline')
      expect(await headline.evaluate((element) => element.tagName)).toBe('TEXTAREA')
      expect(
        await headline.evaluate((element) => element.scrollHeight <= element.clientHeight),
      ).toBe(true)
    }
    await page.screenshot({
      path: test.info().outputPath(`${stage}-${width}.png`),
      fullPage: true,
      animations: 'disabled',
    })
  }
  if (originalViewport) await page.setViewportSize(originalViewport)
}

async function reachValidatedCV(page: Page) {
  await page.goto('/')
  await page.getByLabel('Add or correct profile information').fill('My profile evidence.')
  await page.getByRole('button', { name: 'Add to profile' }).click()
  await page.getByRole('button', { name: 'Confirm these facts' }).click()
  await page.getByRole('button', { name: 'Create resume entries' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await page.getByRole('button', { name: 'Job matches' }).click()
  await page.getByRole('button', { name: 'Retrieve top 3 jobs' }).click()
  await page.getByRole('button', { name: 'Select this job' }).first().click()
  await page.getByRole('button', { name: 'Generate evidence-backed CV' }).click()
  await page.getByRole('button', { name: 'Validate evidence' }).click()
  await expect(page.getByText('Download PDF', { exact: true })).toBeVisible()
}

test('requires review, saved entry wording and explicit approval before jobs', async ({ page }) => {
  await installSuccessfulApi(page)
  await page.goto('/')
  await page.getByLabel('Add or correct profile information').fill('My profile evidence.')
  await page.getByRole('button', { name: 'Add to profile' }).click()
  await page.getByRole('button', { name: 'Confirm these facts' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await page.getByRole('button', { name: 'Create resume entries' }).click()
  await expect(page.getByRole('heading', { name: 'Course planning API' })).toBeVisible()
  await expect(page.locator('.entry-source-list')).toContainText('Built and tested a Python course-planning API.')
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
  await page.getByLabel('Heading', { exact: true }).fill('Python course-planning API')
  await page.getByLabel('Bullet 1', { exact: true }).fill('Built a course-planning API in Python.')
  await expect(page.getByRole('button', { name: 'Approve entry' })).toBeDisabled()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Needs review', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  await expect(page.getByLabel('Bullet 1', { exact: true })).toHaveValue('Built a course-planning API in Python.')
  await checkResponsiveLayout(page, 'review')
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
  await page.getByRole('button', { name: 'Remove entry' }).click()
  await expect(page.getByRole('button', { name: 'Create resume entries' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
})

test('rejected export never downloads a PDF', async ({ page }) => {
  await installSuccessfulApi(page)
  await reachValidatedCV(page)
  await page.route('**/cvs/cv-1/export', async (route) => {
    if (route.request().method() === 'OPTIONS') return route.fallback()
    await fulfill(route, { error: { code: 'invalid_transition',
      message: 'Only the current validated CV can be exported.', details: {} } }, 409)
  })
  const downloads: string[] = []
  page.on('download', (download) => downloads.push(download.suggestedFilename()))
  await page.getByText('Download PDF', { exact: true }).click()
  await expect(page.getByRole('alert').first()).toContainText('Only the current validated CV')
  await page.waitForTimeout(300)
  expect(downloads).toEqual([])
})

test('keeps a long headline fully visible at desktop and phone widths', async ({ page }) => {
  await installSuccessfulApi(page)
  await reachValidatedCV(page)
  const headline = page.getByLabel('Professional headline')
  const longHeadline = 'Computing Science student with Python APIs, applied AI coursework, retrieval evaluation, automated testing, SQL, documentation and team project experience. '.repeat(5)
  await headline.fill(longHeadline)
  await expect(headline).toHaveValue(longHeadline)
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => headline.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true)
  }
})

test('selects two jobs sequentially and requires a new validated CV for the second PDF', async ({ page }) => {
  await installSuccessfulApi(page)
  const generatedTargets: string[] = []
  const exports: string[] = []
  page.on('response', async (response) => {
    if (response.request().method() === 'POST' && response.url().endsWith('/cvs')) {
      const result = await response.json() as { cv: CVDocument }
      generatedTargets.push(result.cv.target_job_id)
    }
  })
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/export')) exports.push(request.url())
  })
  await reachValidatedCV(page)
  const firstDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download PDF' }).click()
  await firstDownload
  await page.getByRole('button', { name: 'Job matches' }).click()
  await page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'AI Engineer', exact: true }) })
    .getByRole('button', { name: 'Select this job' }).click()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Generate evidence-backed CV' })).toBeVisible()
  await expect(page.getByLabel('Professional headline')).toHaveCount(0)
  await page.getByRole('button', { name: 'Generate evidence-backed CV' }).click()
  await expect.poll(() => generatedTargets).toEqual(['graduate_ai_engineer', 'rag_agent_engineer'])
  await expect(page.getByText('Validate this exact draft to unlock PDF export.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  await expect(page.locator('body')).not.toContainText(/graduate_ai_engineer|rag_agent_engineer|cv-1|cv-2/)
  await page.getByRole('button', { name: 'Validate evidence' }).click()
  const secondDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download PDF' }).click()
  await secondDownload
  expect(exports.map((url) => new URL(url).pathname)).toEqual([
    '/api/sessions/session-00000001/cvs/cv-1/export',
    '/api/sessions/session-00000001/cvs/cv-2/export',
  ])
  await page.getByRole('button', { name: 'Job matches' }).click()
  await expect(page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'AI Engineer', exact: true }) })
    .getByRole('button', { name: 'Selected', exact: true })).toBeDisabled()
  await expect(page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Graduate AI Engineer', exact: true }) })
    .getByRole('button', { name: 'Select this job' })).toBeEnabled()
})

test('mock API rejects foreign session IDs and incorrect methods', async ({ page }) => {
  await installSuccessfulApi(page, 'session-owner')
  await page.goto('/')
  const statuses = await page.evaluate(async () => {
    const wrongSession = await fetch('http://localhost:8000/api/sessions/session-foreign/messages', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'Wrong session' }),
    })
    const wrongMethod = await fetch('http://localhost:8000/api/sessions/session-owner/messages')
    return [wrongSession.status, wrongMethod.status]
  })
  expect(statuses.every((status) => status >= 400)).toBe(true)
})

test('completes the guided workflow and re-locks export after an edit', async ({ page }) => {
  await installSuccessfulApi(page)
  await page.goto('/')

  await expect(page.getByRole('button', { name: /Job matches/ })).toBeDisabled()
  await checkResponsiveLayout(page, 'profile')
  await page.getByLabel('Add or correct profile information').fill(
    'I am a third-year Computing Science student seeking graduate AI work.',
  )
  await page.getByRole('button', { name: 'Add to profile' }).click()
  await page.getByRole('button', { name: 'Confirm these facts' }).click()

  await page.getByRole('button', { name: 'Create resume entries' }).click()
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await page.getByRole('button', { name: 'Job matches' }).click()
  await expect(page.getByRole('heading', { name: 'Find your strongest matches' })).toBeVisible()
  await page.getByRole('button', { name: 'Retrieve top 3 jobs' }).click()
  await expect(page.getByText('Develop and evaluate machine-learning models and AI agents.')).toBeVisible()
  await expect(page.getByText('Relevant to your confirmed profile').first()).toBeVisible()
  await expect(page.getByText('Why this appeared').first()).toBeVisible()
  await checkResponsiveLayout(page, 'jobs')
  await page.getByRole('button', { name: 'Select this job' }).first().click()

  await page.getByRole('button', { name: 'Generate evidence-backed CV' }).click()
  await expect(page.getByRole('heading', { name: 'Shape and verify your CV' })).toBeVisible()
  await expect(page.getByLabel('Technical skills statement 1')).toHaveValue('Python')
  await expect(page.getByText('Validate this exact draft to unlock PDF export.')).toBeVisible()
  await checkResponsiveLayout(page, 'cv')
  await page.getByRole('button', { name: 'Validate evidence' }).click()
  const downloadLink = page.getByRole('button', { name: 'Download PDF' })
  await expect(downloadLink).toBeVisible()
  const exportResponse = page.waitForResponse((response) => response.url().endsWith('/export'))
  const download = page.waitForEvent('download')
  await downloadLink.click()
  expect((await exportResponse).ok()).toBe(true)
  await download

  await page.getByLabel('Technical skills statement 1').fill('Python APIs')
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  const saveResponse = page.waitForResponse((response) => response.url().endsWith('/cvs/cv-1') && response.request().method() === 'PUT')
  await page.getByRole('button', { name: 'Save changes' }).click()
  const saved = await (await saveResponse).json() as Session
  expect(saved.cv?.sections[0].claims[0].text).toBe('Python APIs')
  expect(saved.cv?.sections[0].claims[0].verified).toBe(false)
  await expect(page.getByLabel('Technical skills statement 1')).toHaveValue('Python APIs')

  await page.getByLabel('Professional headline').fill('Edited headline awaiting review')
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  await expect(page.getByText('Save your current edits first.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Validate evidence' })).toBeDisabled()
  await page.getByRole('button', { name: /Evidence/ }).click()
  await expect(page.getByRole('heading', { name: 'See why every output exists' })).toBeVisible()
  await expect(page.locator('body')).toContainText('entry-session-00000001')
  await expect(page.locator('body')).toContainText('fact-project')
  await expect(page.locator('body')).toContainText('message-1')
  await expect(page.locator('body')).toContainText('graduate_ai_engineer')
  await expect(page.getByText('User exported the locally rendered PDF.')).toBeVisible()
  await checkResponsiveLayout(page, 'evidence')
})

test('revising a confirmed profile removes the stale job and CV workflow', async ({ page }) => {
  const revisedFacts = profileFacts.map((fact) => fact.field === 'project' ? {
      ...fact,
      value: 'Built a retrieval evaluation prototype with Python.',
      source: { source_type: 'user_message' as const, reference: 'message-2' },
    } : fact)

  await installSuccessfulApi(page, 'session-profile-revision', profileFacts, revisedFacts)

  await reachValidatedCV(page)

  await page.getByRole('button', { name: 'Profile' }).click()
  await page.getByLabel('Add or correct profile information').fill(
    'I also built a retrieval evaluation prototype with Python.',
  )
  await page.getByRole('button', { name: 'Add to profile' }).click()

  await expect(page.getByText('Built a retrieval evaluation prototype with Python.', { exact: true })).toBeVisible()
  await expect(page.getByText('Ready for your review')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Resume entries' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Evidence' }).click()
  await expect(page.locator('body')).toContainText('Status: needs review')
  await expect(page.getByText('Retrieve jobs to inspect the ranking audit.')).toBeVisible()
  await expect(page.getByText('Generate a CV to see claim mappings.')).toBeVisible()
  await page.getByRole('button', { name: 'Profile' }).click()
  await page.getByRole('button', { name: 'Confirm these facts' }).click()
  await expect(page.getByText('Needs review', { exact: true })).toBeVisible()
  await expect(page.locator('.entry-source-list')).toContainText('Built a retrieval evaluation prototype with Python.')
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await page.getByLabel('Bullet 1', { exact: true }).fill('Built a retrieval evaluation prototype with Python.')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
})

test('committed profile update followed by provider failure removes stale CV and recovers', async ({ page }) => {
  const revised = profileFacts.map((fact) => fact.field === 'project'
    ? { ...fact, value: 'Built a new Python chatbot.' } : fact)
  await installSuccessfulApi(page, 'session-partial-failure', profileFacts, revised, true)
  await reachValidatedCV(page)
  await page.getByRole('button', { name: 'Profile' }).click()
  await page.getByLabel('Add or correct profile information').fill('Built a new Python chatbot.')
  await page.getByRole('button', { name: 'Add to profile' }).click()
  await expect(page.getByRole('alert')).toContainText('Provider failed after saving')
  await expect(page.getByRole('button', { name: 'CV studio' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Resume entries' })).toBeDisabled()
  await expect(page.getByText('Built a new Python chatbot.', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toHaveCount(0)
  await page.getByLabel('Add or correct profile information').fill('Continue')
  await page.getByRole('button', { name: 'Add to profile' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Confirm these facts' })).toBeEnabled()
  await page.getByRole('button', { name: 'Confirm these facts' }).click()
  await expect(page.getByText('Needs review', { exact: true })).toBeVisible()
  await expect(page.locator('.entry-source-list')).toContainText('Built a new Python chatbot.')
  await expect(page.getByText(/Review the wording against your confirmed facts/)).toBeVisible()
  await page.getByLabel('Bullet 1', { exact: true }).fill('Built a new Python chatbot.')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByRole('button', { name: 'Approve entry' }).click()
  await expect(page.getByRole('button', { name: 'Job matches' })).toBeEnabled()
})

test('keeps independent browser workspaces visibly isolated', async ({ browser }) => {
  const mayaContext = await browser.newContext()
  const tariqContext = await browser.newContext()
  const maya = await mayaContext.newPage()
  const tariq = await tariqContext.newPage()
  const tariqFacts = profileFacts.map((fact) =>
    fact.fact_id === 'fact-name' ? { ...fact, value: 'Tariq Ahmed' } : fact,
  )

  try {
    await installSuccessfulApi(maya, 'session-browser-maya', profileFacts)
    await installSuccessfulApi(tariq, 'session-browser-tariq', tariqFacts)
    await Promise.all([maya.goto('/'), tariq.goto('/')])

    await expect(maya.locator('.session-badge')).toHaveAttribute('title', 'Temporary workspace')
    await expect(tariq.locator('.session-badge')).toHaveAttribute('title', 'Temporary workspace')
    await expect(maya.getByText('session-browser-maya')).toHaveCount(0)
    await expect(tariq.getByText('session-browser-tariq')).toHaveCount(0)

    await maya.getByLabel('Add or correct profile information').fill('Maya has applied AI coursework.')
    await tariq.getByLabel('Add or correct profile information').fill('Tariq has data engineering coursework.')
    await Promise.all([
      maya.getByRole('button', { name: 'Add to profile' }).click(),
      tariq.getByRole('button', { name: 'Add to profile' }).click(),
    ])

    await expect(maya.getByText('Maya Chen')).toBeVisible()
    await expect(tariq.getByText('Tariq Ahmed')).toBeVisible()
    await expect(maya.getByText('Tariq Ahmed')).toHaveCount(0)
    await expect(tariq.getByText('Maya Chen')).toHaveCount(0)
    await expect(maya.getByText('Maya has applied AI coursework.')).toBeVisible()
    await expect(tariq.getByText('Tariq has data engineering coursework.')).toBeVisible()
    await maya.getByRole('button', { name: 'Confirm these facts' }).click()
    await maya.getByRole('button', { name: 'Create resume entries' }).click()
    await maya.getByRole('button', { name: 'Approve entry' }).click()
    await expect(maya.getByRole('button', { name: 'Job matches' })).toBeEnabled()
    await expect(tariq.getByRole('button', { name: 'Job matches' })).toBeDisabled()
    await expect(tariq.getByRole('button', { name: 'Resume entries' })).toBeDisabled()
    await tariq.getByRole('button', { name: 'Confirm these facts' }).click()
    await tariq.getByRole('button', { name: 'Create resume entries' }).click()
    await expect(tariq.getByText('Proposed', { exact: true })).toBeVisible()
    await expect(maya.getByText('Approved', { exact: true })).toBeVisible()
    await Promise.all([
      maya.getByRole('button', { name: 'Evidence' }).click(),
      tariq.getByRole('button', { name: 'Evidence' }).click(),
    ])
    await expect(maya.locator('body')).toContainText('entry-session-browser-maya')
    await expect(maya.locator('body')).not.toContainText('entry-session-browser-tariq')
    await expect(tariq.locator('body')).toContainText('entry-session-browser-tariq')
    await expect(tariq.locator('body')).not.toContainText('entry-session-browser-maya')
  } finally {
    await Promise.all([mayaContext.close(), tariqContext.close()])
  }
})

test('shows a recoverable provider failure without losing the session', async ({ page }) => {
  const session = initialSession('session-00000002')
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': request.headers().origin ?? '*',
          'access-control-allow-methods': 'GET,POST,OPTIONS',
          'access-control-allow-headers': 'content-type',
        },
      })
      return
    }
    const path = new URL(request.url()).pathname
    if (path === `/api/sessions/${session.session_id}/messages` && request.method() === 'POST') {
      await fulfill(
        route,
        {
          error: {
            code: 'provider_unavailable',
            message: 'The AI provider is unavailable. Check the local configuration and try again.',
            details: {},
          },
        },
        503,
      )
      return
    }
    if (path === '/api/sessions' && request.method() === 'POST') {
      await fulfill(route, session, 201)
    } else if (path === `/api/sessions/${session.session_id}` && request.method() === 'GET') {
      await fulfill(route, session)
    } else {
      await fulfill(route, { error: { code: 'unexpected_route', message: path, details: {} } }, 404)
    }
  })

  await page.goto('/')
  await page.getByLabel('Add or correct profile information').fill('A synthetic test introduction')
  await page.getByRole('button', { name: 'Add to profile' }).click()

  await expect(page.getByRole('alert')).toContainText('The AI provider is unavailable')
  await expect(page.locator('.session-badge')).toHaveAttribute('title', 'Temporary workspace')
  await expect(page.getByRole('heading', { name: 'Build your evidence profile' })).toBeVisible()
})
