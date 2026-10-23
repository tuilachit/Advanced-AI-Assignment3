import { useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../../api'
import type { CreateInterviewRequest, Interview, Session } from '../../types'
import {
  canPrepareInterview, defaultSetupForm, interviewPayload, setupContextKey,
  type InterviewSetupFormState,
} from './setup'

interface PreparedInterview {
  interview: Interview
  contextKey: string
}

function preparationError(reason: unknown): string {
  if (reason instanceof ApiError) {
    if (reason.code === 'cv_not_validated') {
      return 'This CV is no longer validated. Return to CV studio to validate it, or prepare without a CV.'
    }
    if (reason.code === 'interview_not_ready') {
      return 'Your profile or resume entries have changed. Review and approve them before trying again.'
    }
    return reason.message
  }
  return 'The local API could not be reached. Check the connection and try again. Your setup is kept here.'
}

export function useInterviewSetup(session: Session) {
  const contextKey = setupContextKey(session)
  const [editing, setEditing] = useState<{ contextKey: string; form: InterviewSetupFormState } | null>(null)
  const form = editing?.contextKey === contextKey ? editing.form : defaultSetupForm(session)
  const [prepared, setPrepared] = useState<PreparedInterview | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [failure, setFailure] = useState<{ contextKey: string; message: string } | null>(null)
  const inFlight = useRef(false)
  const mounted = useRef(true)
  const lastRequest = useRef<{ fingerprint: string; body: CreateInterviewRequest } | null>(null)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  function updateForm(change: Partial<InterviewSetupFormState>) {
    if (inFlight.current) return
    setEditing({ contextKey, form: { ...form, ...change } })
    setFailure(null)
  }

  async function prepare() {
    if (inFlight.current || !canPrepareInterview(session, form)) return
    const payload = interviewPayload(session, form)
    const fingerprint = JSON.stringify([contextKey, payload])
    if (lastRequest.current?.fingerprint !== fingerprint) {
      lastRequest.current = { fingerprint, body: { ...payload, request_id: crypto.randomUUID() } }
    }
    inFlight.current = true
    setPreparing(true)
    setFailure(null)
    try {
      const interview = await api.createInterview(session.session_id, lastRequest.current.body)
      if (mounted.current) setPrepared({ interview, contextKey })
    } catch (reason) {
      if (mounted.current) setFailure({ contextKey, message: preparationError(reason) })
    } finally {
      inFlight.current = false
      if (mounted.current) setPreparing(false)
    }
  }

  function prepareAnother() {
    if (inFlight.current) return
    setPrepared(null)
    setFailure(null)
    lastRequest.current = null
    // Consent must be given explicitly for each new interview.
    setEditing({ contextKey, form: { ...form, consent: {
      send_audio_to_provider: false, retain_transcript_for_feedback: false,
    } } })
  }

  return {
    updateInterview: (interview: Interview) => setPrepared((previous) => previous ? { ...previous, interview } : null),
    form, updateForm, prepare, prepareAnother, preparing,
    error: failure?.contextKey === contextKey ? failure.message : null,
    interview: prepared?.interview ?? null,
    contextChanged: Boolean(prepared && prepared.contextKey !== contextKey),
  }
}
