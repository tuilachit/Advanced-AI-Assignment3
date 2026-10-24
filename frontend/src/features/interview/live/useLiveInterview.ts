import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../api'
import type { Interview } from '../../../types'
import { canApplySnapshot, initialLiveState, isTerminal, liveReducer, type LiveAction } from './liveState'
import type { VoiceController, VoiceIntegration } from './voiceBridge'

export function useLiveInterview(initial: Interview, integration: VoiceIntegration, visible: boolean) {
  const [state, setState] = useState(() => initialLiveState(initial))
  const [controller, setController] = useState<VoiceController | null>(null)
  const [checking, setChecking] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [attached, setAttached] = useState(false)
  const current = useRef(state)
  // Controller events may arrive in one batch before React renders. Async
  // guards must see the latest accepted event, especially terminal snapshots.
  const dispatch = useCallback((event: LiveAction) => {
    current.current = liveReducer(current.current, event)
    setState(current.current)
  }, [])
  const command = useRef(0)
  const locked = useRef(false)
  const refreshRef = useRef<() => Promise<void>>(async () => {})
  const cancelCommand = useCallback(() => {
    command.current++
    locked.current = false
    setPending(null)
  }, [])

  useEffect(() => {
    const voice = integration.createController(initial.session_id)
    setController(voice)
    setAttached(false)
    setChecking(true)
    setApiError(null)
    cancelCommand()
    dispatch({ type: 'connection', status: 'disconnected' })
    dispatch({ type: 'clear-error' })
    let disposed = false
    let reading = false
    async function refresh() {
      if (disposed || reading) return
      reading = true
      try {
        const interview = await integration.readInterview(initial.session_id, initial.interview_id)
        if (!disposed && canApplySnapshot(current.current.interview, interview)) {
          dispatch({ type: 'snapshot', interview })
          setApiError(null)
          if (isTerminal(interview)) { cancelCommand(); voice?.disconnect() }
        }
      } catch (error) {
        if (!disposed && !isTerminal(current.current.interview)) setApiError(error instanceof ApiError && ['interview_not_found', 'session_not_found'].includes(error.code)
          ? 'This temporary interview is no longer available. Return to setup to prepare another.'
          : 'The local API could not be reached. Displayed progress may be out of date. Retry the connection.')
      } finally {
        reading = false
        if (!disposed) setChecking(false)
      }
    }
    refreshRef.current = refresh
    const unsubscribe = voice?.subscribe((event) => {
      if (disposed) return
      dispatch(event)
      if (event.type === 'finished' && isTerminal(current.current.interview)) {
        cancelCommand()
        setApiError(null)
      }
      if (event.type === 'question' || (event.type === 'connection' && event.status === 'connected')) void refresh()
    })
    void refresh()
    // Luke's controller polls for voice lifecycle changes but does not publish
    // full active/finalizing snapshots. Keep this read-only poll for the timer,
    // saved transcript and question progress. Only his controller performs POSTs.
    const poll = window.setInterval(() => {
      const latest = current.current
      if (['active', 'finalizing'].includes(latest.interview.phase) ||
        ['connecting', 'connected'].includes(latest.connection)) void refresh()
    }, 2000)
    const onPageHide = () => {
      cancelCommand()
      voice?.disconnect()
      dispatch({ type: 'connection', status: 'disconnected' })
    }
    const onPageShow = () => { void refresh() }
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pageshow', onPageShow)
    return () => {
      disposed = true
      command.current++
      locked.current = false
      refreshRef.current = async () => {}
      window.clearInterval(poll)
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('pageshow', onPageShow)
      unsubscribe?.()
      voice?.disconnect()
    }
  }, [initial.session_id, initial.interview_id, integration, cancelCommand, dispatch])

  function disconnect() {
    cancelCommand()
    controller?.disconnect()
    dispatch({ type: 'connection', status: 'disconnected' })
  }

  // The app keeps setup mounted when navigating away. Release audio even then;
  // disconnect never claims the interview ended, and its server timer continues.
  useEffect(() => {
    if (!visible) {
      cancelCommand()
      controller?.disconnect()
      dispatch({ type: 'connection', status: 'disconnected' })
    }
  }, [visible, controller, cancelCommand, dispatch])

  async function run(name: string, action: (voice: VoiceController) => Promise<void | Interview>) {
    if (!controller || locked.current || !visible || isTerminal(current.current.interview)) return
    locked.current = true
    const identity = ++command.current
    setPending(name)
    dispatch({ type: 'clear-error' })
    try {
      const result = await action(controller)
      if (identity === command.current) {
        if (result) dispatch({ type: 'snapshot', interview: result })
        await refreshRef.current()
      }
    } catch {
      if (identity === command.current) {
        // A rejected finish leaves Luke's controller in its draining state.
        // Release it through the public API so an explicit reconnect can recover.
        if (name === 'finish') controller.disconnect()
        if (name === 'connect' && current.current.connection === 'connecting') {
          dispatch({ type: 'connection', status: 'failed' })
        }
        dispatch({ type: 'command-error',
          message: 'That action could not be completed. Your transcript is kept here; check the connection and try again.' })
        // Start/end may already have reached the server before a later step
        // failed. Reload its phase and deadline without repeating any action.
        await refreshRef.current()
      }
    } finally {
      if (identity === command.current) { locked.current = false; setPending(null) }
    }
  }

  return {
    state, controller, checking, apiError, pending, attached,
    refresh: () => refreshRef.current(), disconnect,
    connect: () => run('connect', async (voice) => {
      // Luke's connect() selects the interview before requesting a microphone.
      // A fresh controller has no selected interview, even for an active record.
      setAttached(true)
      dispatch({ type: 'connection', status: 'connecting' })
      await voice.connect(initial.interview_id)
    }),
    skip: () => run('skip', (voice) => voice.skip()),
    finish: () => run('finish', (voice) => voice.finish()),
    resumeAudio: () => run('audio', (voice) => voice.resume_audio()),
    toggleMute: () => {
      if (!controller || state.connection !== 'connected') return
      controller.set_muted(!state.activity.muted)
    },
  }
}
