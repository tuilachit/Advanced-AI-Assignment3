import { expect, test, type Page } from '@playwright/test'

import { interviewSession, preparedInterview } from '../src/test/interviewFixtures'
import type { Interview } from '../src/types'

async function samplePreview(page: Page) {
  const errors: string[] = []
  const requests: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (request.url().includes('/api/') || request.url().includes('api.openai.com')) requests.push(request.url())
  })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
      value: { getUserMedia: () => { throw new Error('Feedback must never request a microphone') } } })
  })
  await page.goto('/feedback-preview.html')
  await expect(page.getByText('Sample feedback · mock data')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Question-by-question feedback' })).toBeVisible()
  return { errors, requests }
}

test('feedback sample displays source-grounded criteria and remains responsive', async ({ page }) => {
  const calls = await samplePreview(page)
  await expect(page.getByText('2 of 3 asked', { exact: true })).toBeVisible()
  await expect(page.getByText('6 min 20 sec', { exact: true })).toBeVisible()
  const firstQuestion = page.locator('.feedback-question').first()
  await expect(firstQuestion.getByLabel('STAR: 2 of 4 — Partially meets the criterion', { exact: true })).toBeVisible()
  await expect(firstQuestion.getByText('Not applicable', { exact: true })).toBeVisible()
  await expect(firstQuestion.getByText('105', { exact: true })).toBeVisible()
  await expect(firstQuestion.getByRole('region', { name: 'Pauses', exact: true }).getByText('Not available', { exact: true })).toBeVisible()
  await expect(page.getByText(/overall score|overall percentage/i)).toHaveCount(0)
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('feedback-top-' + width + '.png'), animations: 'disabled' })
    await page.screenshot({ path: test.info().outputPath('feedback-full-' + width + '.png'), fullPage: true, animations: 'disabled' })
  }
  expect(calls.errors).toEqual([])
  expect(calls.requests).toEqual([])
})

test('question reviews support keyboard expansion, evidence navigation and unavailable metrics', async ({ page }) => {
  const calls = await samplePreview(page)
  await page.locator('.feedback-question').first().getByRole('button', { name: 'View full answer' }).first().click()
  await expect(page.locator('.feedback-transcript')).toHaveAttribute('open', '')
  await expect(page.locator('.feedback-transcript li.is-selected')).toBeFocused()
  await expect(page.locator('.feedback-transcript li.is-selected')).toContainText('I compared two API designs.')
  const technical = page.locator('.feedback-question').filter({ has: page.getByRole('heading', { name: 'How would you test an API before releasing it to users?' }) })
  await technical.locator('summary').first().focus()
  await page.keyboard.press('Enter')
  await expect(technical.getByRole('region', { name: 'STAR evaluation', exact: true }).getByText('Not applicable')).toBeVisible()
  await expect(technical.getByRole('region', { name: 'Speaking pace', exact: true }).getByText('Not available')).toBeVisible()
  await expect(technical.getByRole('region', { name: 'Transcript fillers', exact: true }).getByText('0', { exact: true })).toBeVisible()
  await technical.getByRole('region', { name: 'Pauses', exact: true }).getByText('Method & coverage').click()
  await expect(technical.getByText(/Pauses are not inferred from punctuation/)).toBeVisible()
  const skipped = page.locator('.feedback-question').last()
  await skipped.locator('summary').first().click()
  await expect(skipped.getByText('Insufficient evidence', { exact: true })).toHaveCount(5)
  await expect(skipped.locator('.feedback-score')).toHaveCount(0)
  expect(calls.errors).toEqual([])
  expect(calls.requests).toEqual([])
})

test('feedback preview exposes loading, error and retry without stale data', async ({ page }) => {
  const calls = await samplePreview(page)
  await page.getByLabel('Preview scenario · mock data only').selectOption('retry')
  await expect(page.getByText('Loading sample feedback…', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('sample report could not be loaded')
  await expect(page.locator('.feedback-score')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('feedback-error.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: 'Retry feedback' }).click()
  await expect(page.getByRole('heading', { name: 'Question-by-question feedback' })).toBeVisible()
  await page.getByLabel('Preview scenario · mock data only').selectOption('loading')
  await expect(page.getByText('Loading sample feedback…', { exact: true })).toBeVisible()
  await expect(page.locator('.feedback-score')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('feedback-loading.png'), fullPage: true, animations: 'disabled' })
  await page.getByLabel('Preview scenario · mock data only').selectOption('ready')
  await expect(page.getByRole('heading', { name: 'Question-by-question feedback' })).toBeVisible()
  expect(calls.errors).toEqual([])
  expect(calls.requests).toEqual([])
})

test('missing transcripts and empty interviews show honest unavailable states', async ({ page }) => {
  const calls = await samplePreview(page)
  await page.getByLabel('Preview scenario · mock data only').selectOption('insufficient')
  await expect(page.getByText('Insufficient evidence', { exact: true })).toHaveCount(5)
  await expect(page.getByText('Not available', { exact: true })).toHaveCount(3)
  await expect(page.locator('.feedback-score, .feedback-metric-value')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('feedback-unavailable.png'), fullPage: true, animations: 'disabled' })
  await page.getByLabel('Preview scenario · mock data only').selectOption('empty')
  await expect(page.getByText('No questions were available to review', { exact: true })).toBeVisible()
  await expect(page.getByText('0 of 0 asked', { exact: true })).toBeVisible()
  await expect(page.locator('.feedback-score')).toHaveCount(0)
  expect(calls.errors).toEqual([])
  expect(calls.requests).toEqual([])
})

test('live preview completion hands off to a separate sample and returns without starting audio', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => { if (request.url().includes('/api/')) requests.push(request.url()) })
  await page.goto('/interview-preview.html')
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByText(/I built a small prototype/)).toBeVisible()
  await page.getByRole('button', { name: 'End interview', exact: true }).click()
  await page.getByRole('button', { name: 'Finish interview', exact: true }).click()
  await expect(page.getByRole('button', { name: 'View feedback', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View feedback', exact: true }).click()
  await expect(page.getByText('UI preview · simulated interview summary', { exact: true })).toBeVisible()
  await expect(page.getByText('Feedback is not connected yet', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View sample feedback' }).click()
  await expect(page.getByText('Sample feedback · mock data')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Question-by-question feedback' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to your interview summary' }).click()
  await page.getByRole('button', { name: 'Back to interview', exact: true }).click()
  await expect(page.getByText('Interview complete', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reconnect voice', exact: true })).toBeDisabled()
  expect(requests).toEqual([])
})

test('main application keeps completed interview context separate from sample feedback and preserves CV export', async ({ page }) => {
  const session = interviewSession()
  let interview: Interview | null = null
  const unexpected: string[] = []
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/sessions' && request.method() === 'POST') await route.fulfill({ status: 201, json: session })
    else if (path.endsWith('/interviews') && request.method() === 'POST') {
      interview = preparedInterview(request.postDataJSON(), session)
      await route.fulfill({ status: 201, json: interview })
    } else if (path.endsWith('/interviews/prepared-interview') && request.method() === 'GET' && interview) {
      interview = { ...interview, phase: 'completed', flow_revision: 2, started_at: '2026-10-23T01:00:00Z',
        ended_at: '2026-10-23T01:01:00Z', end_reason: 'user_finished' }
      await route.fulfill({ json: interview })
    } else { unexpected.push(request.method() + ' ' + path); await route.abort() }
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Practise interview' }).click()
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview' }).click()
  await page.getByRole('button', { name: 'Open interview room' }).click()
  await page.getByRole('button', { name: 'View feedback', exact: true }).click()
  await expect(page.getByText('1 min 0 sec', { exact: true })).toBeVisible()
  await expect(page.locator('.feedback-score')).toHaveCount(0)
  await page.getByRole('button', { name: 'View sample feedback' }).click()
  await expect(page.getByText('6 min 20 sec', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Back to your interview summary' }).click()
  await expect(page.getByText('1 min 0 sec', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'CV studio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await expect(page.getByText('1 min 0 sec', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Back to setup' }).click()
  await expect(page.getByText('Interview completed', { exact: true })).toBeVisible()
  expect(unexpected).toEqual([])
})
