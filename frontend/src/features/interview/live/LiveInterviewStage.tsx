import { useEffect, useState } from 'react'

import type { Interview } from '../../../types'
import { InterviewTranscript } from './InterviewTranscript'
import { InterviewerVisualizer, visualizerCopy } from './InterviewerVisualizer'
import { isTerminal, remainingSeconds, visualizerState } from './liveState'
import { useLiveInterview } from './useLiveInterview'
import { voiceIntegration, type VoiceIntegration } from './voiceBridge'
import './liveInterview.css'

interface LiveInterviewStageProps {
  interview: Interview
  visible?: boolean
  integration?: VoiceIntegration
  preview?: boolean
  onClose: (interview: Interview) => void
  onFeedback?: (interview: Interview) => void
}

export function LiveInterviewStage({ interview: initial, visible = true, integration = voiceIntegration,
  preview = false, onClose, onFeedback }: LiveInterviewStageProps) {
  const live = useLiveInterview(initial, integration, visible)
  const { interview, connection, activity, error } = live.state
  const [now, setNow] = useState(() => Date.now())
  const [confirmFinish, setConfirmFinish] = useState(false)
  const terminal = isTerminal(interview)
  useEffect(() => {
    if (terminal) return
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [terminal])
  const seconds = remainingSeconds(interview, now)
  const expired = interview.started_at !== null && seconds === 0 && !terminal
  const finalizing = interview.phase === 'finalizing' || expired
  const connected = connection === 'connected'
  const pending = live.pending !== null
  const canTalk = connected && interview.phase === 'active' && !pending && !finalizing
  const mains = interview.questions.filter((question) => question.kind === 'main')
  const question = interview.questions.find((item) => item.question_id === interview.current_question_id)
  const mainId = question?.kind === 'follow_up' ? question.parent_question_id : question?.question_id
  const mainNumber = mains.findIndex((item) => item.question_id === mainId) + 1
  const completed = mains.filter((item) => ['answered', 'skipped'].includes(item.status)).length
  const state = finalizing ? 'finalizing' : visualizerState(live.state)
  const [label, hint] = visualizerCopy[state]
  const Visualizer = integration.Visualizer ?? InterviewerVisualizer
  const connectionLabel = { disconnected: 'Disconnected', connecting: 'Connecting', connected: 'Connected', failed: 'Connection lost' }[connection]
  const microphoneLabel = preview ? 'Microphone off · simulated'
    : connection === 'connecting' ? 'Microphone access requested · connecting'
      : connected ? activity.muted ? 'Microphone muted' : 'Microphone on' : 'Microphone off'

  return <section className="stage-panel live-interview" aria-labelledby="live-interview-title">
    {preview ? <div className="live-preview-label" role="note"><strong>UI preview · simulated interview</strong>
      <span>Synthetic transcript. No microphone, provider connection, or saved interview.</span></div> : null}
    <div className="section-heading"><div><p className="eyebrow">Interview practice</p>
      <h2 id="live-interview-title">A conversation about your experience</h2></div>
      <button className="interview-text-button" type="button" onClick={() => { live.disconnect(); onClose(interview) }}>
        {terminal ? 'Back to setup' : 'Leave interview room'}</button></div>
    <p className="section-copy live-role">{interview.job.title} <span>· {interview.config.interview_type} interview</span></p>

    <div className="live-workspace">
      <div className="live-conversation">
        <div className="live-session-bar">
          <span className={'status-pill ' + (connected ? 'success' : '')} role="status">{preview ? 'Simulated · ' : ''}{connectionLabel}</span>
          <span className="live-timer" data-urgent={seconds <= 60 && interview.started_at !== null}>
            <span>{!interview.started_at ? 'Time limit' : terminal ? 'Time remaining at end' : 'Time remaining'}</span>
            <span role="timer" aria-label="Interview time remaining" aria-live="off">{Math.floor(seconds / 60).toString().padStart(2, '0')}:{(seconds % 60).toString().padStart(2, '0')}</span>
          </span>
        </div>
        <div className="live-visualizer-slot"><Visualizer state={state} interview={interview} controller={live.controller} />
          <div className="live-activity" role="status"><h3>{interview.phase === 'cancelled' ? 'Interview cancelled'
            : interview.phase === 'failed' ? 'Interview ended with an error' : label}</h3><p>{interview.phase === 'failed'
              ? 'The session ended before it could finish. Your available transcript is below.' : hint}</p></div>
        </div>
        <section className="live-question" aria-labelledby="current-question-title">
          <div className="live-progress-label"><h3 id="current-question-title">{question ? `Question ${mainNumber || '—'} of ${mains.length}` : 'Your first question'}
            {question?.kind === 'follow_up' ? ' · Follow-up' : ''}</h3><span>{completed} of {mains.length} main questions completed or skipped</span></div>
          <progress value={completed} max={mains.length || 1} aria-label="Main question progress" />
          <p role="status">{question?.text ?? (terminal ? 'No question was issued in this interview.' : 'Start your interview to hear the first question.')}</p>
        </section>

        {!live.controller ? <p className="interview-notice">Live voice is not available in this version yet. {interview.started_at
          ? 'Your interview keeps its server time limit. Your microphone is off.'
          : 'Your prepared interview is kept; the microphone and timer stay off until voice is connected.'}</p> : null}
        {live.checking ? <p role="status">Checking your interview…</p> : null}
        {live.apiError ? <div className="error-banner live-error" role="alert"><p>{live.apiError}</p>
          <button type="button" className="secondary-button" onClick={() => void live.refresh()}>Retry status check</button></div> : null}
        {error ? <div className="error-banner live-error" role="alert"><p>{error.message}</p>
          {error.code === 'audio_playback_blocked' ? <button type="button" className="secondary-button" disabled={pending || !connected}
            onClick={() => void live.resumeAudio()}>Enable audio</button> : null}</div> : null}
        {finalizing ? <p role="status" className="interview-notice">{expired ? 'Time limit reached. Waiting for the server to confirm completion.' :
          'Finishing the transcript. Keep this room open for a moment; new answers are disabled.'}</p> : null}
        {terminal ? <div className="live-complete" role="status"><strong>{interview.phase === 'completed' ? 'Interview complete' : 'Interview ended'}</strong>
          <p>{interview.end_reason === 'time_limit' ? 'Your time limit was reached. ' : interview.end_reason === 'questions_complete'
            ? 'You have reached the end of the questions. ' : ''}Your available transcript remains here.</p>
          {interview.phase === 'completed' && onFeedback ? <button type="button" className="primary-button"
            onClick={() => { live.disconnect(); onFeedback(interview) }}>View feedback</button> : null}</div> : null}

        <div className="live-controls" aria-label="Interview controls">
          {!connected ? <button type="button" className="primary-button" disabled={!live.controller || pending || connection === 'connecting' || live.checking || Boolean(live.apiError) || finalizing || terminal || error?.retryable === false}
            onClick={() => void live.connect()}>{connection === 'connecting' ? 'Connecting…' : interview.started_at ? 'Reconnect voice' : 'Start interview'}</button> : null}
          <button type="button" className="secondary-button live-mic-button" aria-pressed={activity.muted}
            disabled={!canTalk} onClick={live.toggleMute}>{activity.muted ? 'Unmute microphone' : 'Mute microphone'}</button>
          <button type="button" className="secondary-button" disabled={!canTalk || !question || Boolean(live.apiError)} onClick={() => void live.skip()}>
            {live.pending === 'skip' ? 'Skipping…' : 'Skip question'}</button>
          <button type="button" className="live-end-button" disabled={!live.controller || !live.attached || pending || interview.phase !== 'active' || finalizing}
            onClick={() => setConfirmFinish(true)}>End interview</button>
          {connected || connection === 'connecting' ? <button type="button" className="interview-text-button" onClick={live.disconnect}>Disconnect voice</button> : null}
        </div>
        <p className="live-microphone-state" role="status">{microphoneLabel}</p>
        {live.controller && !live.attached && interview.phase === 'active' ? <p className="live-session-note">Reconnect voice to attach the controls to this active interview.</p> : null}
        {confirmFinish && !terminal && !finalizing ? <div className="live-finish-confirm" role="group" aria-labelledby="finish-confirm-title">
          <h3 id="finish-confirm-title">Finish this interview?</h3><p>Your captured answers will finish transcribing. You can’t resume a completed interview.</p>
          <div><button type="button" className="live-end-button" disabled={pending} onClick={() => { setConfirmFinish(false); void live.finish() }}>Finish interview</button>
            <button type="button" className="secondary-button" onClick={() => setConfirmFinish(false)}>Keep practising</button></div>
        </div> : null}
        {!terminal && interview.started_at ? <p className="live-session-note">Muting, disconnecting or leaving this room does not pause the time limit. Reconnecting repeats the current question.</p> : null}
      </div>
      <InterviewTranscript turns={interview.turns} />
    </div>
  </section>
}
