import { useState } from 'react'

import type { Interview } from '../../../types'
import { InterviewerVisualizer } from '../live/InterviewerVisualizer'
import type { VisualizerState } from '../live/voiceBridge'
import './orbStatePreview.css'

const states: { state: VisualizerState; label: string; description: string }[] = [
  { state: 'speaking', label: 'Interviewer speaking', description: 'An organic blue breath, drifting gradients and slow outward halos.' },
  { state: 'user-speaking', label: 'Candidate speaking', description: 'A steadier sage core with clearer, quicker outward ripples.' },
  { state: 'listening', label: 'Listening', description: 'A quiet breath while the interviewer waits.' },
  { state: 'connecting', label: 'Connecting', description: 'A slow orbit while the connection is being established.' },
  { state: 'muted', label: 'Muted', description: 'Still, softened colour with a microphone-off symbol.' },
  { state: 'disconnected', label: 'Disconnected', description: 'A still orb and broken ring until you reconnect.' },
  { state: 'ready', label: 'Ready', description: 'At rest before the interview starts.' },
  { state: 'error', label: 'Needs attention', description: 'A quiet amber outline. The error message explains what to do.' },
  { state: 'finalizing', label: 'Finishing', description: 'A slow orbit while the final transcript is saved.' },
  { state: 'finished', label: 'Complete', description: 'A settled sage orb with a completion mark.' },
]

// Development entry only. These fixed presentation states never enter the live
// reducer or controller, and closing the gallery unmounts its animations.
export function OrbStatePreview({ interview }: { interview: Interview }) {
  const [open, setOpen] = useState(false)
  return <details className="orb-state-preview" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Orb states · visual review</summary>
    {open ? <section aria-label="Simulated orb states">
      <p>Fixed visual samples, not a live interview. Motion represents status, not measured audio volume.
        No microphone or provider is used. Your system’s reduced-motion preference applies here too.</p>
      <div className="orb-state-grid">{states.map(({ state, label, description }) =>
        <article key={state} data-preview-state={state}>
          <InterviewerVisualizer state={state} interview={interview} controller={null} />
          <h3>{label}</h3><p>{description}</p>
        </article>)}</div>
    </section> : null}
  </details>
}
