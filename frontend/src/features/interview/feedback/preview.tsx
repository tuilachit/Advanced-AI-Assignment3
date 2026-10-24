import { useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'

import '../../../styles.css'
import '../interview.css'
import { FeedbackStage } from './FeedbackStage'
import { createSampleFeedback, type SampleScenario } from './sampleFeedback'

function FeedbackPreview() {
  const [scenario, setScenario] = useState<SampleScenario>('ready')
  const sample = useMemo(() => createSampleFeedback(scenario), [scenario])
  return <div className="app-shell"><header className="topbar"><div className="brand-mark" aria-hidden="true">e<span>.</span></div>
    <div className="brand-copy"><strong>Evidence CV</strong><span>A little clarity for your next chapter.</span></div>
    <a className="interview-text-button" href="/" style={{ marginLeft: 'auto' }}>Return to CV Builder</a></header>
    <main className="main-content"><FeedbackStage key={scenario} interview={sample.interview} source={sample.source}
      backLabel="Open Live Interview preview" onBack={() => { window.location.href = '/interview-preview.html' }} />
      <section className="feedback-preview-tools" aria-label="Feedback preview controls"><label htmlFor="feedback-scenario">Preview scenario · mock data only</label>
        <select id="feedback-scenario" value={scenario} onChange={(event) => setScenario(event.target.value as SampleScenario)}>
          <option value="ready">Complete sample report</option><option value="retry">Loading error, then successful retry</option>
          <option value="loading">Keep loading</option><option value="insufficient">Missing transcript and unavailable metrics</option>
          <option value="empty">No questions asked</option>
        </select><p>These scenarios make no API, microphone or provider requests.</p></section>
    </main></div>
}

if (import.meta.env.DEV) createRoot(document.getElementById('root')!).render(<FeedbackPreview />)
