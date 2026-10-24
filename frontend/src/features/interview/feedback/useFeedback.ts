import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../api'
import type { Interview } from '../../../types'
import { reportMatchesInterview, type FeedbackReadState, type FeedbackSource } from './feedbackView'

type LoadState = FeedbackReadState | { status: 'loading' } | { status: 'error'; message: string; retryable: boolean }
const snapshotConflicts = new Set(['transcript_revision_conflict', 'feedback_snapshot_conflict',
  'feedback_state_changed', 'invalid_interview_phase', 'request_id_conflict', 'interview_not_found', 'session_not_found'])

function pollDelay(signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, 2000)
    signal.addEventListener('abort', done, { once: true })
    if (signal.aborted) done()
  })
}

export function useFeedback(interview: Interview, source: FeedbackSource | null, visible = true) {
  const identity = JSON.stringify([interview.session_id, interview.interview_id, interview.context_hash, interview.transcript_revision, interview.phase])
  const [result, setResult] = useState<{ identity: string; source: FeedbackSource; state: LoadState } | null>(null)
  const active = useRef<AbortController | null>(null)
  const request = useRef<{ identity: string; id: string } | null>(null)
  const currentInterview = useRef(interview)
  currentInterview.current = interview
  const run = useCallback(async (generate = false) => {
    const snapshot = currentInterview.current
    if (!source || !visible || snapshot.phase !== 'completed' || active.current) return
    const controller = new AbortController()
    const { signal } = controller
    active.current = controller
    const publish = (state: LoadState) => {
      if (signal.aborted) return
      if (state.status === 'ready' && !reportMatchesInterview(state.report, snapshot)) {
        state = { status: 'error', retryable: false,
          message: 'This report does not match the current interview or transcript. Return to the interview to reload its final transcript.' }
      }
      setResult({ identity, source, state })
    }
    publish({ status: generate ? 'generating' : 'loading' })
    try {
      if (source.kind === 'sample') publish({ status: 'ready', report: await source.load(snapshot, signal) })
      else {
        if (generate) {
          if (request.current?.identity !== identity) request.current = { identity, id: crypto.randomUUID() }
          await source.generate(snapshot, request.current.id, signal)
        }
        // POST always returns generating, even for a reused ready evaluation.
        // Only GET determines readiness. Poll serially; never schedule/retry via GET.
        while (!signal.aborted) {
          const next = await source.read(snapshot, signal)
          publish(next)
          if (next.status !== 'generating' || signal.aborted) break
          await pollDelay(signal)
        }
      }
    } catch (error) {
      const conflict = error instanceof ApiError && snapshotConflicts.has(error.code)
      const missing = error instanceof ApiError && ['interview_not_found', 'session_not_found'].includes(error.code)
      publish({ status: 'error', retryable: !conflict,
        message: missing ? 'This temporary interview is no longer available. Return to setup to prepare another interview.'
          : conflict ? 'The interview or transcript has changed. Return to the interview to reload its final transcript before generating feedback.'
          : source.kind === 'sample' ? 'The sample report could not be loaded. Retry to load the example again.'
            : 'Feedback could not be loaded. Your interview is kept. Retry to check the latest status before requesting generation again.' })
    } finally {
      if (active.current === controller) active.current = null
    }
  }, [identity, source, visible])

  useEffect(() => {
    void run()
    return () => { active.current?.abort(); active.current = null }
  }, [run])

  const state = result?.identity === identity && result.source === source ? result.state : { status: 'loading' } as const
  // A transport retry only reads status: the preceding POST may have succeeded.
  return { state, retry: () => run(), generate: () => run(true) }
}
