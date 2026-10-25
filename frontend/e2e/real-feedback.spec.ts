import { expect, test, type Page } from '@playwright/test'
import { feedbackFixture, feedbackResponse } from '../src/test/feedbackFixtures'
import { interviewSession } from '../src/test/interviewFixtures'
import type { FeedbackRequest, FeedbackResponse } from '../src/types'

async function enterFeedback(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Practise interview', exact: true }).click()
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview', exact: true }).click()
  await page.getByRole('button', { name: 'Open interview room', exact: true }).click()
  await page.getByRole('button', { name: 'View feedback', exact: true }).click()
}

async function backend(page: Page, result: () => FeedbackResponse, generate: (body: FeedbackRequest) => void) {
  const { interview, report } = feedbackFixture()
  const unexpected: string[] = []
  const errors: string[] = []
  const requests: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    requests.push(method + ' ' + path)
    const base = '/api/sessions/' + interview.session_id + '/interviews'
    if (path === '/api/sessions' && method === 'POST') await route.fulfill({ status: 201, json: interviewSession() })
    else if (path === base && method === 'POST') await route.fulfill({ status: 201, json: { ...interview, phase: 'ready' } })
    else if (path === base + '/' + interview.interview_id && method === 'GET') await route.fulfill({ json: interview })
    else if (path === base + '/' + interview.interview_id + '/feedback') {
      if (method === 'POST') {
        generate(request.postDataJSON())
        await route.fulfill({ status: 202, json: { feedback_status: 'generating' } })
      } else await route.fulfill({ json: result() })
    } else { unexpected.push(method + ' ' + path); await route.abort() }
  })
  return { interview, report, unexpected, errors, requests }
}

test('completed interview explicitly generates, retries a failed job, and displays API evidence on desktop and mobile', async ({ page }) => {
  const { report } = feedbackFixture()
  let status: FeedbackResponse['feedback_status'] = 'not_requested'
  const writes: FeedbackRequest[] = []
  const calls = await backend(page, () => feedbackResponse(status, status === 'ready' ? report : null), (body) => {
    writes.push(body)
    status = 'generating'
  })
  await enterFeedback(page)
  await expect(page.getByRole('button', { name: 'Generate feedback' })).toBeVisible()
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Generate feedback' }).click()
  await expect(page.getByText('Generating your feedback…', { exact: true })).toBeVisible()
  status = 'failed'
  await expect(page.getByRole('alert')).toContainText('Feedback generation failed')
  expect(writes).toHaveLength(1)
  await page.getByRole('button', { name: 'Retry generation' }).click()
  await expect(page.getByText('Generating your feedback…', { exact: true })).toBeVisible()
  status = 'ready'
  await expect(page.getByText('Feedback ready', { exact: true })).toBeVisible()
  expect(writes).toHaveLength(2)
  expect(writes[0]).toEqual({ request_id: expect.any(String), expected_transcript_revision: calls.interview.transcript_revision })
  expect(writes[1]).toEqual(writes[0])
  const first = page.locator('.feedback-question').first()
  await expect(first.getByLabel('Relevance: 3 of 4 — Clear and well supported')).toBeVisible()
  await expect(first.getByLabel('Specificity: 0 of 4 — Does not address the criterion')).toBeVisible()
  await expect(first.getByText('Explain your own responsibility in the team.')).toBeVisible()
  await expect(first.getByRole('region', { name: 'Speaking pace', exact: true }).getByText('Not available', { exact: true })).toBeVisible()
  await first.getByRole('button', { name: 'View full answer' }).first().click()
  await expect(page.locator('.feedback-transcript li.is-selected')).toBeFocused()
  await expect(page.locator('.feedback-transcript li.is-selected')).toContainText(calls.interview.turns[0].text)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('real-feedback-' + width + '.png'), fullPage: true, animations: 'disabled' })
  }
  const beforeSample = calls.requests.length
  await page.getByRole('button', { name: 'View sample feedback' }).click()
  await expect(page.getByText('Sample feedback · mock data')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Question-by-question feedback' })).toBeVisible()
  expect(calls.requests).toHaveLength(beforeSample)
  await page.getByRole('button', { name: 'Back to your interview summary' }).click()
  await expect(page.getByText('Feedback ready', { exact: true })).toBeVisible()
  expect(writes).toHaveLength(2)
  await page.getByRole('button', { name: 'CV studio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
  expect(calls.unexpected).toEqual([])
  expect(calls.errors).toEqual([])
})

test('a mismatched transcript report is withheld until the canonical interview is refreshed', async ({ page }) => {
  const { report } = feedbackFixture()
  report.transcript_revision++
  const writes: FeedbackRequest[] = []
  const calls = await backend(page, () => feedbackResponse('ready', report), (body) => writes.push(body))
  await enterFeedback(page)
  await expect(page.getByRole('alert')).toContainText('does not match the current interview')
  await expect(page.locator('.feedback-score')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Retry|Generate/ })).toHaveCount(0)
  calls.interview.transcript_revision = report.transcript_revision
  await page.getByRole('button', { name: 'Back to interview', exact: true }).click()
  await expect(page.getByText('Interview complete', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View feedback', exact: true }).click()
  await expect(page.getByText('Feedback ready', { exact: true })).toBeVisible()
  expect(writes).toEqual([])
  expect(calls.unexpected).toEqual([])
  expect(calls.errors).toEqual([])
})
