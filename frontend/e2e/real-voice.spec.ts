import { expect, test } from '@playwright/test'

import type { components } from '../src/generated/api-schema'
import { interviewSession, preparedInterview } from '../src/test/interviewFixtures'
import { feedbackResponse, unassessedFeedback } from '../src/test/feedbackFixtures'
import type { Interview } from '../src/types'

type Hardware = { microphones: number; stopped: number; closed: number; paused: number;
  emit(event: Record<string, unknown>): void }
type VoiceWindow = Window & { voiceHardware: Hardware }

test('main UI uses the real controller, releases voice on navigation and retains the completed transcript for feedback', async ({ page }) => {
  // Replace only browser hardware/SDP and HTTP. This is not the scripted preview.
  await page.addInitScript(() => {
    const hardware: Hardware = { microphones: 0, stopped: 0, closed: 0, paused: 0, emit: () => {} }
    Object.assign(window, { voiceHardware: hardware })
    let stream: MediaStream
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: async () => {
        hardware.microphones++
        stream = new MediaStream()
        const track = { enabled: true, stop: () => { hardware.stopped++ } }
        Object.defineProperty(stream, 'getTracks', { value: () => [track] })
        Object.defineProperty(stream, 'getAudioTracks', { value: () => [track] })
        return stream
      },
    } })
    Object.defineProperty(HTMLMediaElement.prototype, 'paused', { get: () => false })
    HTMLMediaElement.prototype.play = async function () {}
    HTMLMediaElement.prototype.pause = function () { hardware.paused++ }
    class Channel extends EventTarget {
      readyState = 'open'
      close() { this.readyState = 'closed' }
      send() {}
    }
    class Peer extends EventTarget {
      connectionState = 'connected'
      channel = new Channel()
      addTrack() {}
      close() { hardware.closed++ }
      createDataChannel() {
        hardware.emit = (event) => this.channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
        return this.channel
      }
      async createOffer() { return { type: 'offer', sdp: 'test-offer' } }
      async setLocalDescription() {}
      async setRemoteDescription() {
        this.dispatchEvent(Object.assign(new Event('track'), { streams: [stream] }))
      }
    }
    Object.defineProperty(window, 'RTCPeerConnection', { value: Peer })
  })

  const session = interviewSession()
  let interview: Interview | null = null
  let complete = false
  let feedbackRequested = false
  const writes: string[] = []
  const unexpected: string[] = []
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('https://api.openai.com/**', (route) => {
    if (new URL(route.request().url()).pathname !== '/v1/realtime/calls') {
      unexpected.push(route.request().url())
      return route.abort()
    }
    return route.fulfill({ status: 201, body: 'test-answer' })
  })
  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const base = '/api/sessions/' + session.session_id
    if (request.method() === 'POST') writes.push(path)
    if (path === '/api/sessions' && request.method() === 'POST') {
      await route.fulfill({ status: 201, json: session })
      return
    }
    if (path === base + '/interviews' && request.method() === 'POST') {
      interview = preparedInterview(request.postDataJSON(), session)
      await route.fulfill({ status: 201, json: interview })
      return
    }
    const resource = base + '/interviews/prepared-interview'
    if (interview && path === resource + '/feedback') {
      if (request.method() === 'POST') {
        expect(interview.phase).toBe('completed')
        expect(request.postDataJSON()).toEqual({ request_id: expect.any(String), expected_transcript_revision: interview.transcript_revision })
        feedbackRequested = true
        await route.fulfill({ status: 202, json: { feedback_status: 'generating' } })
      } else await route.fulfill({ json: feedbackRequested
        ? feedbackResponse('ready', unassessedFeedback(interview)) : feedbackResponse('not_requested') })
      return
    }
    if (interview && path === resource && request.method() === 'GET') {
      if (complete && interview.phase === 'finalizing') {
        interview.phase = 'completed'
        interview.ended_at = new Date().toISOString()
        interview.flow_revision++
      }
      await route.fulfill({ json: interview })
      return
    }
    if (interview && request.method() === 'POST') {
      if (path === resource + '/start') {
        interview.phase = 'active'
        interview.started_at = new Date().toISOString()
        interview.flow_revision++
        interview.current_question_id = 'question-0'
        interview.questions[0].status = 'issued'
        await route.fulfill({ json: { interview, next_step: { action: 'ask_question',
          question: interview.questions[0], flow_revision: interview.flow_revision } } })
        return
      }
      if (path === resource + '/realtime-token') {
        await route.fulfill({ json: { client_secret: 'ephemeral-test-only', expires_at: 4_000_000_000,
          connection_id: 'browser-test-connection', model: 'test-model' } })
        return
      }
      if (path === resource + '/turns') {
        const body = request.postDataJSON() as components['schemas']['TurnEventRequest']
        const index = interview.turns.findIndex((turn) => turn.turn_id === body.turn.turn_id)
        if (index < 0) interview.turns.push(body.turn)
        else interview.turns[index] = body.turn
        interview.transcript_revision++
        await route.fulfill({ json: { event_id: body.event_id, turn_id: body.turn.turn_id,
          transcript_revision: interview.transcript_revision } })
        return
      }
      if (path === resource + '/skip') {
        interview.questions[0].status = 'skipped'
        interview.questions[1].status = 'issued'
        interview.current_question_id = 'question-1'
        interview.flow_revision++
        await route.fulfill({ json: { action: 'ask_question', question: interview.questions[1],
          flow_revision: interview.flow_revision } })
        return
      }
      if (path === resource + '/end') {
        interview.phase = 'finalizing'
        interview.flow_revision++
        await route.fulfill({ json: interview })
        return
      }
    }
    unexpected.push(request.method() + ' ' + path)
    await route.abort()
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Practise interview', exact: true }).click()
  await page.getByRole('checkbox', { name: /send my audio/ }).check()
  await page.getByRole('checkbox', { name: /keep my transcript/ }).check()
  await page.getByRole('button', { name: 'Prepare interview', exact: true }).click()
  await page.getByRole('button', { name: 'Open interview room', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Start interview', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => (window as VoiceWindow).voiceHardware.microphones)).toBe(0)
  await expect(page.getByText('UI preview · simulated interview')).toHaveCount(0)
  await page.getByRole('button', { name: 'Start interview', exact: true }).click()
  await expect(page.getByText('Connected', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Listening', exact: true })).toBeVisible()
  await page.evaluate(() => {
    const emit = (window as VoiceWindow).voiceHardware.emit
    emit({ type: 'input_audio_buffer.speech_started', item_id: 'browser-answer', audio_start_ms: 100 })
    emit({ type: 'input_audio_buffer.speech_stopped', item_id: 'browser-answer', audio_end_ms: 2500 })
    emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'browser-answer',
      transcript: 'I tested the Python API with my team.' })
  })
  await expect(page.getByText('I tested the Python API with my team.')).toBeVisible()
  await page.getByRole('button', { name: 'Mute microphone', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Unmute microphone' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Unmute microphone' }).click()
  await page.getByRole('button', { name: 'Skip question' }).click()
  await expect(page.getByText('Question 2 of 4', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'CV studio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download PDF', exact: true })).toBeVisible()
  expect(await page.evaluate(() => (window as VoiceWindow).voiceHardware.stopped)).toBeGreaterThan(0)
  expect(writes.some((path) => path.endsWith('/end'))).toBe(false)
  await page.getByRole('button', { name: 'Interview', exact: true }).click()
  expect(await page.evaluate(() => (window as VoiceWindow).voiceHardware.microphones)).toBe(1)
  await page.getByRole('button', { name: 'Reconnect voice', exact: true }).click()
  await expect(page.getByText('Connected', { exact: true })).toBeVisible()
  await expect(page.getByText('I tested the Python API with my team.')).toBeVisible()
  await page.getByRole('button', { name: 'End interview', exact: true }).click()
  await page.getByRole('button', { name: 'Finish interview', exact: true }).click()
  await expect(page.getByText(/Finishing the transcript/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'View feedback', exact: true })).toHaveCount(0)
  complete = true
  await expect(page.getByText('Interview complete', { exact: true })).toBeVisible()
  const resources = await page.evaluate(() => {
    const { microphones, stopped, closed, paused } = (window as VoiceWindow).voiceHardware
    return { microphones, stopped, closed, paused }
  })
  expect(resources).toEqual({ microphones: 2, stopped: 2, closed: 2, paused: 2 })
  await page.getByRole('button', { name: 'View feedback', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Turn practice into progress' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Generate feedback', exact: true })).toBeVisible()
  expect(writes.some((path) => path.endsWith('/feedback'))).toBe(false)
  await page.getByRole('button', { name: 'Generate feedback', exact: true }).click()
  await expect(page.getByText('Feedback ready', { exact: true })).toBeVisible()
  // The test deliberately skipped the captured answer: no submitted evidence
  // should be scored merely because its text is present in the final transcript.
  await expect(page.locator('.feedback-score, .feedback-metric-value')).toHaveCount(0)
  await page.getByRole('button', { name: 'Back to interview', exact: true }).click()
  await expect(page.getByText('I tested the Python API with my team.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reconnect voice', exact: true })).toBeDisabled()
  expect(await page.evaluate(() => (window as VoiceWindow).voiceHardware.microphones)).toBe(2)
  expect(writes.filter((path) => path.endsWith('/start'))).toHaveLength(1)
  expect(writes.filter((path) => path.endsWith('/realtime-token'))).toHaveLength(2)
  expect(writes.filter((path) => path.endsWith('/skip'))).toHaveLength(1)
  expect(writes.filter((path) => path.endsWith('/end'))).toHaveLength(1)
  expect(writes.filter((path) => path.endsWith('/feedback'))).toHaveLength(1)
  expect(unexpected).toEqual([])
  expect(errors).toEqual([])
})
