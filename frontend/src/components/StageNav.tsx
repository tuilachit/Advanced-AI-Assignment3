import type { SessionState } from '../types'

export type Stage = 'profile' | 'resume' | 'jobs' | 'cv' | 'interview' | 'evidence'

interface StageNavProps {
  active: Stage
  state: SessionState
  onChange: (stage: Stage) => void
}

const stateOrder: SessionState[] = [
  'collecting_profile',
  'profile_review',
  'profile_confirmed',
  'resume_entries_review',
  'resume_entries_approved',
  'jobs_retrieved',
  'job_selected',
  'cv_draft',
  'cv_validated',
  'pdf_exported',
]

export function stateAtLeast(state: SessionState, minimum: SessionState): boolean {
  return stateOrder.indexOf(state) >= stateOrder.indexOf(minimum)
}

export function preferredStage(state: SessionState): Stage {
  if (stateAtLeast(state, 'job_selected')) return 'cv'
  if (stateAtLeast(state, 'jobs_retrieved')) return 'jobs'
  if (stateAtLeast(state, 'profile_confirmed')) return 'resume'
  return 'profile'
}

export function StageNav({ active, state, onChange }: StageNavProps) {
  const stages: Array<{ id: Stage; label: string; enabled: boolean }> = [
    { id: 'profile', label: 'Profile', enabled: true },
    { id: 'resume', label: 'Resume entries', enabled: stateAtLeast(state, 'profile_confirmed') },
    { id: 'jobs', label: 'Job matches', enabled: stateAtLeast(state, 'resume_entries_approved') },
    { id: 'cv', label: 'CV studio', enabled: stateAtLeast(state, 'job_selected') },
    { id: 'interview', label: 'Interview', enabled: true },
    { id: 'evidence', label: 'Evidence', enabled: true },
  ]

  return (
    <nav className="stage-nav" aria-label="CV builder progress">
      {stages.map((stage, index) => (
        <button
          className={`stage-button ${active === stage.id ? 'is-active' : ''}`}
          disabled={!stage.enabled}
          key={stage.id}
          onClick={() => onChange(stage.id)}
          type="button"
          aria-current={active === stage.id ? 'step' : undefined}
        >
          <span className="stage-index" aria-hidden="true">
            {index + 1}
          </span>
          <span>
            <small>Step {index + 1}</small>
            {stage.label}
          </span>
        </button>
      ))}
    </nav>
  )
}
