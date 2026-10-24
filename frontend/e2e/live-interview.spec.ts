import { expect, test, type Page } from '@playwright/test'

import { interviewSession, preparedInterview } from '../src/test/interviewFixtures'
import type { Interview } from '../src/types'

async function preview(page: Page) {
  const errors: string[] = []
  const apiCalls: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (request.url().includes('/api/') || request.url().includes('api.openai.com')) apiCalls.push(request.url())
  })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
      value: { getUserMedia: () => { throw new Error('UI preview must never request a microphone') } } })
  })
  await page.goto('/interview-preview.html')
  await expect(page.getByText('UI preview · simulated interview')).toBeVisible()
  return { errors, apiCalls }
}

test('live preview starts explicitly, displays captions and remains responsive with no audio or API requests', async ({ page }) => {
  const calls = await preview(page)
  await expect(page.getByRole('timer')).toHaveText('10:00')
  await expect(page.getByText('Start your interview to hear the first question.')).toBeVisible()
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Connecting…' })).toBeDisabled()
  await expect(page.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
  await expect(page.getByText('Question 1 of 4', { exact: true })).toBeVisible()
  await expect(page.getByText('Live caption · may change')).toBeVisible()
  await expect(page.getByText(/I built a small prototype/)).toBeVisible()
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('live-active-' + width + '.png'), fullPage: true, animations: 'disabled' })
  }
  await page.getByRole('button', { name: 'Mute microphone', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Unmute microphone' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: 'Microphone muted', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Unmute microphone' }).click()
  await page.getByRole('button', { name: 'Skip question' }).click()
  await expect(page.getByText('Question 2 of 4', { exact: true })).toBeVisible()
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('preview recovers from connection loss and blocked playback without discarding saved captions', async ({ page }) => {
  const calls = await preview(page)
  await page.getByRole('button', { name: 'Start interview' }).click()
  await expect(page.getByText(/I built a small prototype/)).toBeVisible()
  await page.getByText('Preview controls · synthetic scenarios', { exact: true }).click()
  await page.getByRole('button', { name: 'Simulate connection loss' }).click()
  await expect(page.getByRole('alert')).toContainText('voice connection was lost')
  await expect(page.getByRole('button', { name: 'Skip question' })).toBeDisabled()
  await expect(page.getByText(/I built a small prototype/)).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('live-disconnected.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: 'Reconnect voice' }).click()
  await expect(page.getByRole('button', { name: 'Mute microphone' })).toBeEnabled()
  await page.getByRole('button', { name: 'Simulate blocked audio' }).click()
  await expect(page.getByRole('alert')).toContainText('blocked audio playback')
  await page.getByRole('button', { name: 'Enable audio' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('cancelling a preview connection keeps simulation labels and requires an explicit restart', async ({ page }) => {
  const calls = await preview(page)
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Connecting…' })).toBeDisabled()
  await expect(page.getByText('Microphone off · simulated', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Disconnect voice', exact: true }).click()
  await expect(page.getByText('Simulated · Disconnected', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start interview', exact: true })).toBeEnabled()
  await expect(page.getByText('UI preview · simulated interview')).toBeVisible()
  await expect(page.getByText('Start your interview to hear the first question.')).toBeVisible()
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByText('Simulated · Connected', { exact: true })).toBeVisible()
  await expect(page.getByText('Microphone off · simulated', { exact: true })).toBeVisible()
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('preview confirms finish, waits for finalization and offers feedback', async ({ page }) => {
  const calls = await preview(page)
  await page.getByRole('button', { name: 'Start interview' }).click()
  await expect(page.getByText(/I built a small prototype/)).toBeVisible()
  await page.getByRole('button', { name: 'End interview', exact: true }).click()
  await page.getByRole('button', { name: 'Keep practising' }).click()
  await expect(page.getByRole('button', { name: 'End interview', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'End interview', exact: true }).click()
  await page.getByRole('button', { name: 'Finish interview', exact: true }).click()
  await expect(page.getByText(/Finishing the transcript/)).toBeVisible()
  await expect(page.getByText('Interview complete', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'End interview', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'View feedback', exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('live-completed.png'), fullPage: true, animations: 'disabled' })
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('preview respects reduced motion and explains denied microphone access', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const calls = await preview(page)
  await page.getByRole('button', { name: 'Start interview' }).click()
  await expect(page.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
  expect(await page.locator('.interviewer-orb').evaluate((node) => getComputedStyle(node).animationName)).toBe('none')
  await page.getByText('Preview controls · synthetic scenarios', { exact: true }).click()
  await page.getByRole('button', { name: 'Simulate microphone denial' }).click()
  await expect(page.getByRole('alert')).toContainText('Microphone access was denied')
  await expect(page.getByRole('button', { name: 'Reconnect voice' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Unmute microphone' })).toBeDisabled()
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('CV setup opens the live room with voice available but never starts a microphone automatically', async ({ page }) => {
  const session = interviewSession()
  let interview: Interview | null = null
  const unexpected: string[] = []
  let reads = 0
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
      value: { getUserMedia: () => { throw new Error('Microphone requires an explicit Start action') } } })
  })
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/sessions' && request.method() === 'POST') await route.fulfill({ status: 201, json: session })
    else if (path.endsWith('/interviews') && request.method() === 'POST') {
      interview = preparedInterview(request.postDataJSON(), session)
      await route.fulfill({ status: 201, json: interview })
    } else if (path.endsWith('/interviews/prepared-interview') && request.method() === 'GET') {
      reads++
      await route.fulfill({ json: interview })
    } else { unexpected.push(request.method() + ' ' + path); await route.abort() }
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Practise interview' }).click()
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview' }).click()
  await page.getByRole('button', { name: 'Open interview room' }).click()
  await expect(page.getByRole('heading', { name: 'A conversation about your experience' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start interview' })).toBeEnabled()
  await expect(page.getByText('Microphone off', { exact: true })).toBeVisible()
  await expect(page.getByText(/Live voice is not available/)).toHaveCount(0)
  await page.getByRole('button', { name: 'CV studio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'A conversation about your experience' })).toBeVisible()
  await page.getByRole('button', { name: 'Leave interview room' }).click()
  await expect(page.getByText('Interview prepared', { exact: true })).toBeVisible()
  expect(reads).toBe(1)
  expect(unexpected).toEqual([])
})
