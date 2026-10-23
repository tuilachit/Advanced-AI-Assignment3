import { useCallback, useEffect, useRef, useState } from 'react'

import type { Interview } from '../../../types'
import { reportMatchesInterview, type FeedbackSource, type FeedbackView } from './feedbackView'

type LoadState = { status: 'loading' } | { status: 'ready'; report: FeedbackView } | { status: 'error'; message: string }

export function useFeedback(interview: Interview, source: FeedbackSource | null) {
  const identity = JSON.stringify([interview.interview_id, interview.context_hash, interview.transcript_revision, interview.phase])
  const [result, setResult] = useState<{ identity: string; source: FeedbackSource; state: LoadState } | null>(null)
  const active = useRef<AbortController | null>(null)
  const currentInterview = useRef(interview)
  currentInterview.current = interview
  const load = useCallback(async () => {
    const snapshot = currentInterview.current
    if (!source || snapshot.phase !== 'completed' || active.current) return
    const controller = new AbortController()
    active.current = controller
    setResult({ identity, source, state: { status: 'loading' } })
    try {
      const report = await source.load(snapshot, controller.signal)
      if (controller.signal.aborted) return
      if (!reportMatchesInterview(report, snapshot)) {
        setResult({ identity, source, state: { status: 'error',
          message: 'This report does not match the current interview or transcript. Reload feedback to get the right version.' } })
      } else setResult({ identity, source, state: { status: 'ready', report } })
    } catch {
      if (!controller.signal.aborted) setResult({ identity, source, state: { status: 'error',
        message: source.kind === 'sample' ? 'The sample report could not be loaded. Retry to load the example again.'
          : 'Feedback could not be loaded. Your interview is kept. Check the connection and try again.' } })
    } finally {
      if (active.current === controller) active.current = null
    }
  }, [identity, source])

  useEffect(() => {
    void load()
    return () => { active.current?.abort(); active.current = null }
  }, [load])

  const state = result?.identity === identity && result.source === source ? result.state : { status: 'loading' } as const
  return { state, retry: load }
}
