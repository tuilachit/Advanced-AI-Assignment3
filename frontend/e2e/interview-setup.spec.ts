import { expect, test, type Page } from '@playwright/test'

import { interviewSession, preparedInterview } from '../src/test/interviewFixtures'
import type { CreateInterviewRequest, Session } from '../src/types'

async function installApi(page: Page, session: Session) {
  const creations: CreateInterviewRequest[] = []
  const unexpected: string[] = []
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/sessions' && request.method() === 'POST') {
      await route.fulfill({ json: session, status: 201 })
    } else if (path === '/api/sessions/' + session.session_id + '/interviews' && request.method() === 'POST') {
      const body = request.postDataJSON() as CreateInterviewRequest
      creations.push(body)
      await route.fulfill({ json: preparedInterview(body, session), status: 201 })
    } else {
      unexpected.push(request.method() + ' ' + path)
      await route.fulfill({ status: 500, json: { error: { code: 'unexpected_route', message: path, details: {} } } })
    }
  })
  return { creations, unexpected }
}

test('setup is discoverable before profile completion and responsive without starting audio', async ({ page }) => {
  const session: Session = { ...interviewSession(), state: 'collecting_profile',
    profile: { facts: [], revision: 0 }, resume_entries: [], retrieval_results: [],
    selected_job_id: null, cv: null, validated_content_hash: null }
  const calls = await installApi(page, session)
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.goto('/')
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Prepare for your next conversation' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Prepare interview', exact: true })).toBeDisabled()
  await expect(page.getByText('Microphone off', { exact: true })).toBeVisible()
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('setup-locked-' + width + '.png'), fullPage: true, animations: 'disabled' })
  }
  await page.getByRole('button', { name: 'Review profile', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Build your evidence profile' })).toBeVisible()
  expect(calls.creations).toHaveLength(0)
  expect(calls.unexpected).toEqual([])
  expect(pageErrors).toEqual([])
})

test('validated CV hands off to setup, retains navigation state, and prepares through the API', async ({ page }) => {
  const calls = await installApi(page, interviewSession())
  await page.goto('/')
  await page.getByRole('button', { name: 'Practise interview', exact: true }).click()
  await expect(page.getByLabel('Target job', { exact: true })).toHaveValue('job-1')
  await expect(page.getByRole('checkbox', { name: /Include my current validated CV/ })).toBeChecked()
  await page.getByLabel('Interview focus').selectOption('technical')
  await page.getByLabel('Time limit').selectOption('5')
  await page.getByRole('button', { name: 'CV studio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download PDF', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await expect(page.getByLabel('Interview focus')).toHaveValue('technical')
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('setup-ready-' + width + '.png'), fullPage: true, animations: 'disabled' })
  }
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview', exact: true }).click()
  await expect(page.getByText('Interview prepared', { exact: true })).toBeVisible()
  expect(calls.creations).toHaveLength(1)
  expect(calls.creations[0]).toMatchObject({
    cv_id: 'validated-cv', job: { source: 'supplied_job', document_id: 'job-1' },
    config: { interview_type: 'technical', duration_minutes: 5 },
    consent: { send_audio_to_provider: true, retain_transcript_for_feedback: true },
  })
  await page.getByRole('button', { name: 'Evidence', exact: true }).click()
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await expect(page.getByText('Interview prepared', { exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('interview-prepared-375.png'), fullPage: true, animations: 'disabled' })
  expect(calls.unexpected).toEqual([])
})

test('pasted role works without a CV and does not change the CV Builder job selection', async ({ page }) => {
  const session: Session = { ...interviewSession(), state: 'resume_entries_approved',
    cv: null, validated_content_hash: null, selected_job_id: null, retrieval_results: [] }
  const calls = await installApi(page, session)
  await page.goto('/')
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await page.getByLabel('Job title', { exact: true }).fill('Graduate Developer')
  await page.getByLabel('Job description', { exact: true }).fill('Build and test reliable Python APIs.')
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview', exact: true }).click()
  await expect(page.getByText('Interview prepared', { exact: true })).toBeVisible()
  expect(calls.creations[0]).toMatchObject({ cv_id: null,
    job: { source: 'pasted_job', title: 'Graduate Developer', description: 'Build and test reliable Python APIs.' } })
  expect(calls.unexpected).toEqual([])
})

test('shows planning and provider errors, then retries the same request safely', async ({ page }) => {
  await installApi(page, interviewSession())
  const requests: CreateInterviewRequest[] = []
  let releaseResponse!: () => void
  const waiting = new Promise<void>((resolve) => { releaseResponse = resolve })
  await page.route('**/interviews', async (route) => {
    const body = route.request().postDataJSON() as CreateInterviewRequest
    requests.push(body)
    if (requests.length === 1) {
      await waiting
      await route.fulfill({ status: 503, json: { error: {
        code: 'provider_unavailable', message: 'The question planner is unavailable. Please try again.', details: {},
      } } })
    } else {
      await route.fulfill({ status: 201, json: preparedInterview(body) })
    }
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Preparing interview…' })).toBeDisabled()
  await expect(page.getByLabel('Target job', { exact: true })).toBeDisabled()
  await expect(page.getByText(/Preparing questions from your confirmed experience/)).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('setup-preparing.png'), fullPage: true, animations: 'disabled' })
  releaseResponse()
  await expect(page.getByRole('alert')).toContainText('The question planner is unavailable.')
  await page.screenshot({ path: test.info().outputPath('setup-provider-error.png'), fullPage: true, animations: 'disabled' })
  await expect(page.getByRole('checkbox', { name: /keep my transcript/ })).toBeChecked()
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByText('Interview prepared', { exact: true })).toBeVisible()
  expect(requests).toHaveLength(2)
  expect(requests[0].request_id).toBe(requests[1].request_id)
})
