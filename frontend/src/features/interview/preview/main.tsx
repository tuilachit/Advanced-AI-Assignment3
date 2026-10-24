import { useState } from 'react'
import { createRoot } from 'react-dom/client'

import '../../../styles.css'
import '../interview.css'
import { LiveInterviewStage } from '../live/LiveInterviewStage'
import { InterviewFeedback } from '../feedback/InterviewFeedback'
import { PreviewVoiceController, previewInterview } from './previewController'

function LivePreview() {
  const [controller] = useState(() => new PreviewVoiceController())
  const [interview, setInterview] = useState(previewInterview)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  return <div className="app-shell">
    <header className="topbar"><div className="brand-mark" aria-hidden="true">e<span>.</span></div>
      <div className="brand-copy"><strong>Evidence CV</strong><span>A little clarity for your next chapter.</span></div>
      <a className="interview-text-button" href="/" style={{ marginLeft: 'auto' }}>Return to CV Builder</a></header>
    <main className="main-content">{feedbackOpen ? <><div className="live-preview-label" role="note"><strong>UI preview · simulated interview summary</strong>
      <span>This summary comes from the scripted preview. No real audio was recorded.</span></div>
      <InterviewFeedback interview={interview} source={null}
        onBack={() => setFeedbackOpen(false)} onSetup={() => { window.location.href = '/' }} /></>
      : <LiveInterviewStage interview={interview} integration={controller.integration}
        preview onClose={() => { window.location.href = '/' }}
        onFeedback={(completed) => { setInterview(completed); setFeedbackOpen(true) }} />}
      {!feedbackOpen ? <details className="live-preview-tools"><summary>Preview controls · synthetic scenarios</summary>
        <p>These controls simulate UI notifications. They do not test a real device or provider.</p>
        <div className="live-controls">
          <button className="secondary-button" onClick={() => controller.simulateFailure('voice_disconnected')}>Simulate connection loss</button>
          <button className="secondary-button" onClick={() => controller.simulateFailure('microphone_denied')}>Simulate microphone denial</button>
          <button className="secondary-button" onClick={() => controller.simulateFailure('audio_playback_blocked')}>Simulate blocked audio</button>
          <button className="secondary-button" onClick={() => window.location.reload()}>Reset preview</button>
        </div></details> : null}
    </main></div>
}

// Vite serves this separate HTML entry for local UI review only. The normal
// production build has a single index.html entry and does not include this page.
if (import.meta.env.DEV) createRoot(document.getElementById('root')!).render(<LivePreview />)
