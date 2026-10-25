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

test('orb follows voice states without audio analysis and settles after mute or disconnect', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-24T10:10:00Z') })
  await page.clock.pauseAt(new Date('2026-10-24T10:10:01Z'))
  const calls = await preview(page)
  const orb = page.locator('.live-interview .interviewer-visualizer')
  const animations = () => orb.evaluate((node) => node.getAnimations({ subtree: true })
    .filter((animation) => animation.effect?.getTiming().iterations === Infinity).length)
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(orb).toHaveAttribute('data-state', 'connecting')
  await expect.poll(animations).toBeGreaterThan(0)
  await page.clock.runFor(700)
  await expect(orb).toHaveAttribute('data-state', 'speaking')
  await expect(page.getByRole('heading', { name: 'Your interviewer is speaking' })).toBeVisible()
  const interviewerAppearance = await orb.locator('.interviewer-orb-current--sage').evaluate((node) => getComputedStyle(node).opacity)
  await page.clock.runFor(1800)
  await expect(orb).toHaveAttribute('data-state', 'user-speaking')
  await expect(page.getByRole('heading', { name: 'You have the floor' })).toBeVisible()
  await expect.poll(() => orb.locator('.interviewer-orb-current--sage').evaluate((node) => getComputedStyle(node).opacity))
    .not.toBe(interviewerAppearance)
  await expect.poll(() => orb.locator('.interviewer-orbit').evaluate((node) => getComputedStyle(node, '::after').opacity))
    .not.toBe('0')
  await expect.poll(animations).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Mute microphone', exact: true }).click()
  await expect(orb).toHaveAttribute('data-state', 'muted')
  await expect.poll(animations).toBe(0)
  await page.getByRole('button', { name: 'Disconnect voice', exact: true }).click()
  await expect(orb).toHaveAttribute('data-state', 'disconnected')
  await expect(page.getByRole('heading', { name: 'Voice disconnected' })).toBeVisible()
  await expect.poll(animations).toBe(0)
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('orb review is isolated, responsive, and disables every animation under reduced motion', async ({ page }) => {
  const calls = await preview(page)
  await page.getByText('Orb states · visual review', { exact: true }).click()
  const gallery = page.getByRole('region', { name: 'Simulated orb states' })
  await expect(gallery.getByRole('article')).toHaveCount(10)
  await expect(gallery).toContainText('Motion represents status, not measured audio volume')
  for (const state of ['connecting', 'listening', 'speaking', 'user-speaking', 'finalizing']) {
    const sample = gallery.locator(`[data-preview-state="${state}"] .interviewer-visualizer`)
    await expect.poll(() => sample.evaluate((node) => node.getAnimations({ subtree: true }).length)).toBeGreaterThan(0)
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect.poll(() => gallery.evaluate((node) => node.getAnimations({ subtree: true }).length)).toBe(0)
  const motionDisabled = () => gallery.locator('.interviewer-visualizer').evaluateAll((orbs) => orbs.every((orb) =>
    [orb, ...orb.querySelectorAll('*')].every((node) => [null, '::before', '::after'].every((pseudo) => {
      const style = getComputedStyle(node, pseudo)
      return style.animationName === 'none' && style.transitionDuration === '0s'
    }))))
  expect(await motionDisabled()).toBe(true)
  for (const width of [1440, 768, 375, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByText('Orb states · visual review', { exact: true }).click()
  await expect(gallery).toHaveCount(0)
  await expect(page.locator('.interviewer-visualizer')).toHaveCount(1)
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

test('speaking ripples move outward at distinct rhythms without moving the layout', async ({ page }) => {
  const calls = await preview(page)
  await page.getByText('Orb states · visual review', { exact: true }).click()
  const gallery = page.getByRole('region', { name: 'Simulated orb states' })
  for (const width of [1440, 375, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    const durations: number[] = []
    for (const state of ['speaking', 'user-speaking']) {
      const sample = gallery.locator(`[data-preview-state="${state}"] .interviewer-visualizer`)
      const result = await sample.evaluate((node) => {
        const animations = node.getAnimations({ subtree: true }).filter((animation) =>
          animation.effect?.getTiming().iterations === Infinity)
        animations.forEach((animation) => animation.pause())
        const ripples = animations.filter((animation) => animation instanceof CSSAnimation &&
          animation.animationName === 'interviewer-ripple-out')
        if (ripples.length !== 2) throw new Error('Both outward ripple surfaces must be animated')
        const duration = Number(ripples[0].effect!.getTiming().duration)
        const layer = node.querySelector('.interviewer-ripples')!
        const core = node.querySelector('.interviewer-orb')!
        const shape = () => {
          const rect = core.getBoundingClientRect()
          return { width: rect.width, height: rect.height }
        }
        const sampleAt = (progress: number) => {
          animations.forEach((animation) => {
            animation.currentTime = Number(animation.effect!.getTiming().duration) * progress
          })
          const ring = getComputedStyle(layer, '::before')
          const frame = node.getBoundingClientRect()
          const heading = node.parentElement!.querySelector('h3')!.getBoundingClientRect()
          return { radius: new DOMMatrixReadOnly(ring.transform).a, opacity: Number(ring.opacity),
            frame: { x: frame.x, y: frame.y, width: frame.width, height: frame.height }, headingTop: heading.top }
        }
        const start = sampleAt(.16)
        const initialShape = shape()
        const end = sampleAt(.72)
        const changedShape = shape()
        const paintOnly = animations.every((animation) => (animation.effect as KeyframeEffect).getKeyframes()
          .every((frame) => Object.keys(frame).every((key) =>
            ['offset', 'computedOffset', 'easing', 'composite', 'transform', 'opacity'].includes(key))))
        const maximumDiameter = parseFloat(getComputedStyle(layer).width) *
          parseFloat(getComputedStyle(node).getPropertyValue('--orb-ripple-end'))
        return { start, end, duration, paintOnly, maximumDiameter, initialShape, changedShape }
      })
      expect(result.end.radius).toBeGreaterThan(result.start.radius)
      expect(result.start.opacity).toBeGreaterThan(result.end.opacity)
      expect(result.end.frame).toEqual(result.start.frame)
      expect(result.end.headingTop).toBe(result.start.headingTop)
      expect(result.maximumDiameter).toBeLessThanOrEqual(result.start.frame.width)
      expect(result.paintOnly).toBe(true)
      if (state === 'speaking') {
        expect(Math.abs(result.initialShape.width - result.changedShape.width)).toBeGreaterThan(3)
      }
      durations.push(result.duration)
    }
    expect(durations[1]).toBeLessThan(durations[0])
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  for (const state of ['ready', 'muted', 'disconnected']) {
    await expect.poll(() => gallery.locator(`[data-preview-state="${state}"]`)
      .evaluate((node) => node.getAnimations({ subtree: true }).length)).toBe(0)
  }
  expect(calls.errors).toEqual([])
  expect(calls.apiCalls).toEqual([])
})

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
  // Hold the simulated handshake pending regardless of browser/CI scheduling.
  await page.clock.install({ time: new Date('2026-10-24T10:10:00Z') })
  await page.clock.pauseAt(new Date('2026-10-24T10:10:01Z'))
  const calls = await preview(page)
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Connecting…' })).toBeDisabled()
  await expect(page.getByText('Microphone off · simulated', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Disconnect voice', exact: true }).click()
  // A cancelled handshake must not activate later when its original deadline passes.
  await page.clock.runFor(700)
  await expect(page.getByText('Simulated · Disconnected', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start interview', exact: true })).toBeEnabled()
  await expect(page.getByText('UI preview · simulated interview')).toBeVisible()
  await expect(page.getByText('Start your interview to hear the first question.')).toBeVisible()
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await page.clock.runFor(700)
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
