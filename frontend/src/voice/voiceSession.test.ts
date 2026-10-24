import { describe, expect, it } from 'vitest'

import { InterviewVoiceSession } from './voiceSession'
import type { InterviewApi, TranscriptTurn, VoiceEvent } from './types'
import { firstQuestion as first, interviewFixture as fixture } from './testFixtures'

function setup(failWrites = false) {
  const saved = new Map<string, TranscriptTurn>()
  const sent: Record<string, unknown>[] = []
  const events: VoiceEvent[] = []
  const steps: unknown[] = []
  const skips: unknown[] = []
  const api: InterviewApi = {
    get: async () => fixture(),
    start: async () => ({ interview: fixture(), next_step: {
      action: 'ask_question', question: first, flow_revision: 1,
    } }),
    token: async () => ({ client_secret: 'ephemeral-fixture', expires_at: 4_000_000_000,
      connection_id: 'c1', model: 'gpt-realtime-2' }),
    turn: async (_id, event) => {
      if (failWrites) throw new Error('Network unavailable')
      saved.set(event.turn.turn_id, structuredClone(event.turn))
      return { event_id: event.event_id, turn_id: event.turn.turn_id,
        transcript_revision: saved.size }
    },
    next: async (_id, body) => {
      steps.push(body)
      return { action: 'ask_question', question: { ...first, question_id: 'q2', text: 'Why SQL?' },
        flow_revision: 2 }
    },
    skip: async (_id, body) => {
      skips.push(body)
      return { action: 'finish', reason: 'questions_complete', flow_revision: 2 }
    },
    end: async () => ({ ...fixture(), phase: 'completed', current_question_id: null }),
  }
  const session = new InterviewVoiceSession({ interview: fixture(), connection_id: 'c1', api,
    send: (event) => sent.push(event), emit: (event) => events.push(event),
    can_hear_audio: () => true, retry_delay_ms: 0 })
  return { session, saved, sent, events, steps, skips, api }
}

function speech(session: InterviewVoiceSession, id = 'candidate-item') {
  session.handle({ type: 'input_audio_buffer.speech_started', item_id: id, audio_start_ms: 1000 })
  session.handle({ type: 'input_audio_buffer.speech_stopped', item_id: id, audio_end_ms: 4000 })
}

function final(session: InterviewVoiceSession, id = 'candidate-item') {
  session.handle({ type: 'conversation.item.input_audio_transcription.completed',
    item_id: id, transcript: 'I wrote tests for the Python API.' })
}

function advance(session: InterviewVoiceSession, args = '{"follow_up_question":"","follow_up_rationale":""}', callId = 'call-one') {
  session.handle({ type: 'response.done', response: { id: `tool-response-${callId}`, status: 'completed',
    output: [{ type: 'function_call', name: 'advance_interview', call_id: callId, arguments: args }] } })
}

describe('native voice transcript and progression', () => {
  it('speaks each newly issued question after playback recovers, without a candidate prompt', async () => {
    const { session, sent, api } = setup()
    let audible = true
    const gated = new InterviewVoiceSession({ interview: fixture(), connection_id: 'c1', api,
      send: event => sent.push(event), emit: () => {}, can_hear_audio: () => audible })
    try {
      gated.askCurrentQuestion()
      gated.handle({ type: 'response.created', response: { id: 'r1' } })
      gated.handle({ type: 'response.done', response: { id: 'r1', status: 'completed', output: [] } })
      audible = false
      speech(gated)
      final(gated)
      advance(gated)
      await gated.flush()
      expect(gated.interview.current_question_id).toBe('q2')
      expect(sent.filter(event => event.type === 'response.create')).toHaveLength(1)
      audible = true
      gated.resumeSpeech()
      expect(sent.filter(event => event.type === 'response.create')).toHaveLength(2)
      expect(sent.at(-1)).toMatchObject({ response: { metadata: { question_id: 'q2' },
        output_modalities: ['audio'], tool_choice: 'none' } })
      gated.resumeSpeech()
      expect(sent.filter(event => event.type === 'response.create')).toHaveLength(2)
    } finally { gated.close(); session.close() }
  })

  it('keeps pending transcript delivery open when Skip reaches finalizing', async () => {
    const { session, events, api, saved } = setup()
    api.get = async () => ({ ...fixture(), phase: 'finalizing', current_question_id: null })
    speech(session)
    await session.skip()
    expect(events.some(event => event.type === 'finished')).toBe(false)
    final(session)
    await session.flush()
    expect([...saved.values()][0]).toMatchObject({ question_id: 'q1', transcript_status: 'final' })
    session.close()
  })

  it('does not register late old-question items when Skip precedes response creation', async () => {
    const { session, saved, api } = setup()
    api.skip = async () => ({ action: 'ask_question', question: { ...first, question_id: 'q2' }, flow_revision: 2 })
    session.askCurrentQuestion()
    await session.skip()
    session.handle({ type: 'response.created', response: { id: 'r1', metadata: { question_id: 'q1' } } })
    session.handle({ type: 'response.output_item.added', response_id: 'r1', item: { id: 'a1', type: 'message', role: 'assistant' } })
    session.handle({ type: 'response.output_audio_transcript.done', response_id: 'r1', item_id: 'a1', transcript: 'Late old question' })
    await session.flush()
    expect(saved.size).toBe(0)
    session.close()
  })

  it('accepts a successful spoken retry while retaining the earlier failed evidence', async () => {
    const { session, saved, steps } = setup()
    speech(session, 'failed')
    session.handle({ type: 'conversation.item.input_audio_transcription.failed', item_id: 'failed' })
    advance(session, '{"follow_up_question":"","follow_up_rationale":""}', 'failed-call')
    await session.flush()
    speech(session, 'retry')
    final(session, 'retry')
    await session.flush()
    expect(steps).toHaveLength(0)
    advance(session)
    await session.flush()
    expect(steps).toHaveLength(1)
    expect([...saved.values()].some(turn => turn.transcript_status === 'failed')).toBe(true)
    expect((steps[0] as { answer_turn_ids: string[] }).answer_turn_ids).toHaveLength(1)
    session.close()
  })

  it('cancels and clears old speech before issuing the skipped-to question', async () => {
    const { session, sent, api } = setup()
    api.skip = async () => ({ action: 'ask_question', question: { ...first, question_id: 'q2' }, flow_revision: 2 })
    session.askCurrentQuestion()
    session.handle({ type: 'response.created', response: { id: 'r1' } })
    session.handle({ type: 'response.output_item.added', response_id: 'r1', item: { id: 'a1', type: 'message', role: 'assistant' } })
    session.handle({ type: 'output_audio_buffer.started', response_id: 'r1' })
    await session.skip()
    expect(sent).toContainEqual({ type: 'response.cancel', response_id: 'r1' })
    expect(sent).toContainEqual({ type: 'output_audio_buffer.clear' })
    expect(sent.filter(event => event.type === 'response.create')).toHaveLength(1)
    session.handle({ type: 'response.done', response: { id: 'r1', status: 'cancelled', output: [] } })
    expect(sent.filter(event => event.type === 'response.create')).toHaveLength(2)
    session.close()
  })

  it('does not append a retried provider delta twice', async () => {
    const { session, events } = setup()
    speech(session)
    const delta = { type: 'conversation.item.input_audio_transcription.delta',
      event_id: 'delta-1', item_id: 'candidate-item', delta: 'Python and SQL' }
    session.handle(delta)
    session.handle(delta)
    const partials = events.filter((event) => event.type === 'transcript' && event.turn.transcript_status === 'partial')
    expect(partials).toHaveLength(1)
    expect(partials[0]).toMatchObject({ turn: { text: 'Python and SQL' } })
    session.close()
  })

  it('preserves the first final transcript against late failures and conflicting completions', async () => {
    const { session, saved } = setup()
    speech(session)
    final(session)
    session.handle({ type: 'conversation.item.input_audio_transcription.failed', item_id: 'candidate-item' })
    session.handle({ type: 'conversation.item.input_audio_transcription.completed',
      item_id: 'candidate-item', transcript: 'Wrong late replacement' })
    await session.flush()
    expect([...saved.values()][0]).toMatchObject({ transcript_status: 'final', text: 'I wrote tests for the Python API.' })
    session.close()
  })

  it('keeps speech order when final transcripts arrive in the reverse order', async () => {
    const { session, saved } = setup()
    speech(session, 'first')
    speech(session, 'second')
    session.handle({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'second', transcript: 'SQL second.' })
    session.handle({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'first', transcript: 'Python first.' })
    await session.flush()
    expect([...saved.values()].map((turn) => turn.text)).toEqual(['Python first.', 'SQL second.'])
    session.close()
  })

  it('requests conversational delivery while retaining the exact authorized question', () => {
    const { session, sent } = setup()
    session.askCurrentQuestion()
    const response = sent[0].response as { instructions: string; tool_choice: string }
    expect(response.instructions).toContain('conversational')
    expect(response.instructions).toContain('pauses')
    expect(response.instructions).toContain(JSON.stringify(first.text))
    expect(response.tool_choice).toBe('none')
    session.close()
  })

  it('replaces partial text and deduplicates final events without losing VAD timings', async () => {
    const { session, saved } = setup()
    speech(session)
    session.handle({ type: 'conversation.item.input_audio_transcription.delta',
      item_id: 'candidate-item', delta: 'I wrote ' })
    final(session)
    final(session)
    await session.flush()
    expect(saved.size).toBe(1)
    const turn = [...saved.values()][0]
    expect(turn.text).toBe('I wrote tests for the Python API.')
    expect(turn.question_id).toBe('q1')
    expect(turn.transcript_status).toBe('final')
    expect(turn.timing).toEqual({ clock_id: 'c1-audio', start_ms: 1000, end_ms: 4000,
      source: 'provider_vad' })
  })

  it('waits for asynchronous final transcription and advances once for a repeated tool call', async () => {
    const { session, steps, sent } = setup()
    speech(session)
    advance(session)
    await session.flush()
    expect(steps).toHaveLength(0)
    final(session)
    await session.flush()
    advance(session)
    await session.flush()
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({ answered_question_id: 'q1', connection_id: 'c1',
      expected_flow_revision: 1, follow_up_proposal: null })
    expect(session.interview.current_question_id).toBe('q2')
    expect(sent.some((event) => event.type === 'response.create')).toBe(true)
  })

  it('never advances when transcript persistence fails', async () => {
    const { session, steps, events } = setup(true)
    speech(session)
    final(session)
    advance(session)
    await session.flush()
    expect(steps).toHaveLength(0)
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'transcript_save_failed' }))
  })

  it('rejects malformed tool arguments without issuing a question', async () => {
    const { session, steps, events } = setup()
    speech(session)
    final(session)
    advance(session, '{"session_id":"other-user"}')
    await session.flush()
    expect(steps).toHaveLength(0)
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'invalid_voice_tool' }))
  })

  it('keeps interrupted output marked interrupted after late completion', async () => {
    const { session, saved } = setup()
    session.askCurrentQuestion()
    session.handle({ type: 'response.created', response: { id: 'r1' } })
    session.handle({ type: 'response.output_item.added', response_id: 'r1',
      item: { id: 'assistant-item', type: 'message', role: 'assistant' } })
    session.handle({ type: 'output_audio_buffer.started', response_id: 'r1' })
    speech(session)
    session.handle({ type: 'response.output_audio_transcript.done', response_id: 'r1',
      item_id: 'assistant-item', transcript: 'How did you test your API?' })
    session.handle({ type: 'output_audio_buffer.stopped', response_id: 'r1' })
    await session.flush()
    expect([...saved.values()].find((turn) => turn.speaker === 'interviewer')?.delivery_status)
      .toBe('interrupted')
  })

  it('waits without advancing when candidate asks for thinking time', async () => {
    const { session, steps, sent } = setup()
    session.handle({ type: 'response.done', response: { id: 'wait-response', status: 'completed',
      output: [{ type: 'function_call', name: 'continue_listening', call_id: 'wait-call', arguments: '{}' }] } })
    await session.flush()
    expect(steps).toHaveLength(0)
    expect(sent.filter((event) => event.type === 'response.create')).toHaveLength(0)
    expect(sent.some((event) => event.type === 'conversation.item.create')).toBe(true)
  })

  it('ignores late events after disconnect', async () => {
    const { session, saved } = setup()
    session.close()
    speech(session)
    final(session)
    await session.flush()
    expect(saved.size).toBe(0)
  })

  it('does not advance a cancelled model tool response', async () => {
    const { session, steps } = setup()
    speech(session)
    final(session)
    session.handle({ type: 'response.function_call_arguments.done', name: 'advance_interview',
      call_id: 'cancelled-call', response_id: 'cancelled-response', arguments: '{"follow_up_proposal":null}' })
    session.handle({ type: 'response.done', response: { id: 'cancelled-response', status: 'cancelled', output: [] } })
    await session.flush()
    expect(steps).toHaveLength(0)
  })

  it('finishes without asking another question when a late tool arrives during transcript drain', async () => {
    const { session, steps } = setup()
    speech(session)
    const finishing = session.finish()
    advance(session)
    final(session)
    await finishing
    expect(steps).toHaveLength(0)
  })

  it('does not skip the next question when an in-flight answer already advanced the flow', async () => {
    const { session, skips } = setup()
    speech(session)
    final(session)
    advance(session)
    await session.skip()
    expect(skips).toHaveLength(0)
  })

  it('cancels unissued model speech instead of storing it as an authorized question', async () => {
    const { session, saved, sent, events } = setup()
    session.handle({ type: 'response.created', response: { id: 'unsolicited' } })
    session.handle({ type: 'response.output_item.added', response_id: 'unsolicited',
      item: { type: 'message', role: 'assistant', id: 'unauthorized-question' } })
    await session.flush()
    expect(saved.size).toBe(0)
    expect(sent).toContainEqual({ type: 'response.cancel', response_id: 'unsolicited' })
    expect(events).toContainEqual(expect.objectContaining({ type: 'error', code: 'unissued_question' }))
  })

  it('handles the provider argument-done event without a name and dispatches its completed response once', async () => {
    const { session, steps } = setup()
    speech(session)
    final(session)
    session.handle({ type: 'response.function_call_arguments.done', call_id: 'native-call',
      item_id: 'native-item', response_id: 'native-response', arguments: '{"follow_up_question":"","follow_up_rationale":""}' })
    session.handle({ type: 'response.done', response: {
      id: 'native-response', status: 'completed', output: [{ type: 'function_call',
        name: 'advance_interview', call_id: 'native-call', arguments: '{"follow_up_question":"","follow_up_rationale":""}' }],
    } })
    await session.flush()
    expect(steps).toHaveLength(1)
    expect(session.interview.current_question_id).toBe('q2')
  })

  it('maps the flat native tool arguments to the unchanged structured backend proposal', async () => {
    const { session, steps } = setup()
    speech(session)
    final(session)
    advance(session, '{"follow_up_question":"How did you test validation?","follow_up_rationale":"The candidate mentioned testing."}')
    await session.flush()
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({ follow_up_proposal: {
      text: 'How did you test validation?', rationale: 'The candidate mentioned testing.',
    } })
  })
})
