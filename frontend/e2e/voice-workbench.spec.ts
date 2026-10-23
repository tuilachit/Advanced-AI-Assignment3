import { expect, test } from '@playwright/test'
import { interviewFixture } from '../src/voice/testFixtures'

test('shows a ready orb only after consent and preparing an interview', async ({ page }) => {
  await page.route('**/api/voice-demo', (route) => route.fulfill({ json: { ...interviewFixture(), phase: 'ready' } }))
  await page.goto('/voice-dev.html')
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'idle')
  await expect(page.locator('#connect')).toBeDisabled()
  await page.locator('#prepare').click()
  await expect(page.locator('#error')).toContainText('agree')
  await page.locator('#consent').check()
  await page.locator('#prepare').click()
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'ready')
  await expect(page.locator('#connect')).toBeEnabled()
})

test('fits a phone screen and disables orb motion for reduced-motion users', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/voice-dev.html')
  const orb = page.locator('#voice-orb')
  await expect(orb).toBeVisible()
  const box = await orb.boundingBox()
  expect(box!.width).toBeGreaterThan(180)
  expect(Math.abs(box!.width - box!.height)).toBeLessThan(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await orb.evaluate((el) => getComputedStyle(el.querySelector('.orb-mist')!).animationName)).toBe('none')
  await expect(page.getByRole('button', { name: 'Mute microphone' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Finish interview' })).toBeVisible()
})

test('wires transport activity, mute and finish to the orb without external API calls', async ({ page }) => {
  // Replace only external transport/hardware; use the real controller, adapter and views.
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => new MediaStream() })
    class Channel extends EventTarget {
      readyState = 'open'
      close() {}
      send(value: string) {
        const event = JSON.parse(value)
        if (event.type !== 'response.create') return
        queueMicrotask(() => {
          for (const data of [
            { type: 'response.created', response: { id: 'r1' } },
            { type: 'response.output_item.added', response_id: 'r1', item: { id: 'a1', type: 'message', role: 'assistant' } },
            { type: 'output_audio_buffer.started', response_id: 'r1' },
          ]) this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(data) }))
        })
      }
    }
    class Peer extends EventTarget {
      connectionState = 'connected'
      channel = new Channel()
      addTrack() {}
      close() {}
      createDataChannel() {
        Object.assign(window, { __emitVoice: (event: unknown) => this.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })) })
        return this.channel
      }
      async createOffer() { return { type: 'offer', sdp: 'fixture-offer' } }
      async setLocalDescription() {}
      async setRemoteDescription() {}
    }
    Object.defineProperty(window, 'RTCPeerConnection', { value: Peer })
  })
  await page.route('**/api/voice-demo', (route) => route.fulfill({ json: interviewFixture() }))
  await page.route('**/api/sessions/s1/interviews/i1**', (route) => {
    const action = new URL(route.request().url()).pathname.split('/').at(-1)
    const body = action === 'realtime-token' ? { client_secret: 'ephemeral-fixture', expires_at: 4_000_000_000, connection_id: 'c1', model: 'gpt-realtime-2' }
      : action === 'end' ? { ...interviewFixture(), phase: 'completed', end_reason: 'user_finished' }
        : action === 'turns' ? { event_id: route.request().postDataJSON().event_id, turn_id: route.request().postDataJSON().turn.turn_id, transcript_revision: 1 }
          : interviewFixture()
    return route.fulfill({ json: body })
  })
  await page.route('https://api.openai.com/v1/realtime/calls', (route) => route.fulfill({ status: 201, body: 'fixture-answer' }))
  await page.goto('/voice-dev.html')
  await page.locator('#consent').check()
  await page.locator('#prepare').click()
  await page.locator('#connect').click()
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'speaking')
  await page.evaluate(() => {
    const emit = (window as unknown as { __emitVoice: (event: unknown) => void }).__emitVoice
    emit({ type: 'input_audio_buffer.speech_started', item_id: 'u1', audio_start_ms: 100 })
  })
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'user-speaking')
  await page.evaluate(() => {
    const emit = (window as unknown as { __emitVoice: (event: unknown) => void }).__emitVoice
    emit({ type: 'input_audio_buffer.speech_stopped', item_id: 'u1', audio_end_ms: 900 })
    emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'u1', transcript: 'I tested the Python API.' })
  })
  await page.getByRole('button', { name: 'Mute microphone', exact: true }).click()
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'muted')
  await expect(page.getByRole('button', { name: 'Unmute microphone' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Finish interview' }).click()
  await expect(page.locator('#voice-orb')).toHaveAttribute('data-state', 'finished')
  await expect(page.locator('#voice-status')).toHaveText('Session complete')
})
