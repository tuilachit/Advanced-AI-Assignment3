import { useEffect, useState } from 'react'

import { ApiError, api } from './api'
import { CVStage } from './components/CVStage'
import { EvidenceStage } from './components/EvidenceStage'
import { JobStage } from './components/JobStage'
import { ProfileStage } from './components/ProfileStage'
import { ResumeEntryStage } from './components/ResumeEntryStage'
import { WorkspaceHero } from './components/WorkspaceHero'
import { preferredStage, StageNav, type Stage } from './components/StageNav'
import { InterviewSetupStage } from './features/interview/InterviewSetupStage'
import type { ChatMessage, CVDocument, ResumeEntry, ResumeEntryEdit, Session } from './types'

interface WorkflowAppProps {
  session: Session
  messages: ChatMessage[]
  busy: boolean
  error: string | null
  onSendMessage: (message: string) => Promise<void>
  onConfirmProfile: () => Promise<void>
  onProposeResumeEntries: () => Promise<void>
  onEditResumeEntry: (entryId: string, edit: ResumeEntryEdit) => Promise<ResumeEntry | void>
  onApproveResumeEntry: (entryId: string) => Promise<void>
  onDeleteResumeEntry: (entryId: string) => Promise<void>
  onRetrieveJobs: () => Promise<void>
  onSelectJob: (documentId: string) => Promise<void>
  onGenerateCV: () => Promise<void>
  onSaveCV: (cv: CVDocument) => Promise<void>
  onValidateCV: (cvId: string) => Promise<void>
  onRecordExport: (cvId: string) => Promise<void>
}

export function WorkflowApp(props: WorkflowAppProps) {
  const { session, error, busy } = props
  const [activeStage, setActiveStage] = useState<Stage>(() => preferredStage(session.state))

  useEffect(() => {
    setActiveStage(preferredStage(session.state))
  }, [session.state])

  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="#main-content" className="skip-link">Skip to content</a>
        <div className="brand-mark" aria-hidden="true">e<span>.</span></div>
        <div className="brand-copy">
          <strong>Evidence CV</strong>
          <span>A little clarity for your next chapter.</span>
        </div>
        <div className="session-badge" title="Temporary workspace">
          <span className="session-dot" aria-hidden="true" /> Personal workspace
        </div>
      </header>

      {activeStage === 'profile' && session.profile.facts.length === 0 ? <WorkspaceHero /> : null}

      <div className="workspace" id="builder">
        <div className="workflow-header">
          <p className="eyebrow">Your experience. Your next step.</p>
          <StageNav active={activeStage} state={session.state} onChange={setActiveStage} />
        </div>

        <main id="main-content" className="main-content">
          {error ? <div className="error-banner" role="alert">{error}</div> : null}
          {busy ? <div className="busy-line" role="status">Working with your evidence…</div> : null}
          {activeStage === 'profile' ? (
            <ProfileStage
              session={session}
              messages={props.messages}
              busy={busy}
              onSendMessage={props.onSendMessage}
              onConfirm={props.onConfirmProfile}
            />
          ) : null}
          {activeStage === 'resume' ? (
            <ResumeEntryStage
              session={session}
              busy={busy}
              onPropose={props.onProposeResumeEntries}
              onEdit={props.onEditResumeEntry}
              onApprove={props.onApproveResumeEntry}
              onDelete={props.onDeleteResumeEntry}
            />
          ) : null}
          {activeStage === 'jobs' ? (
            <JobStage
              session={session}
              busy={busy}
              onRetrieve={props.onRetrieveJobs}
              onSelect={props.onSelectJob}
            />
          ) : null}
          {activeStage === 'cv' ? (
            <CVStage
              session={session}
              busy={busy}
              onGenerate={props.onGenerateCV}
              onSave={props.onSaveCV}
              onValidate={props.onValidateCV}
              onRecordExport={props.onRecordExport}
              onPrepareInterview={() => setActiveStage('interview')}
            />
          ) : null}
          {activeStage === 'evidence' ? <EvidenceStage session={session} /> : null}
          <div hidden={activeStage !== 'interview'}>
            <InterviewSetupStage
              key={session.session_id}
              visible={activeStage === 'interview'}
              session={session}
              busy={busy}
              onReviewProfile={() => setActiveStage('profile')}
              onReviewEntries={() => setActiveStage('resume')}
              onReviewJobs={() => setActiveStage('jobs')}
            />
          </div>
        </main>
      </div>
      <footer className="workspace-footer">
        <span>Evidence CV <span className="footer-divider">/</span> Made from your experience.</span>
        <span><ShieldIcon /> Sessions are temporary. Keep a copy of your PDF.</span>
      </footer>
    </div>
  )
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshFailed, setRefreshFailed] = useState(false)

  useEffect(() => {
    let active = true
    api.createSession()
      .then((created) => { if (active) setSession(created) })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [])

  async function reconcileSession() {
    if (!session) return
    try {
      setSession(await api.getSession(session.session_id))
      setRefreshFailed(false)
    } catch {
      setRefreshFailed(true)
    }
  }

  async function run(operation: () => Promise<Session>, propagateError = false) {
    setBusy(true)
    setError(null)
    try {
      setSession(await operation())
    } catch (reason) {
      setError(errorMessage(reason))
      await reconcileSession()
      if (propagateError) throw reason
    } finally {
      setBusy(false)
    }
  }

  if (!session) {
    return <div className="startup" role={error ? 'alert' : 'status'}>{error || 'Opening your workspace…'}</div>
  }

  if (refreshFailed) {
    return <div className="startup" role="alert">
      <p>{error}</p>
      <p>The latest session could not be loaded. Refresh it to continue.</p>
      <button className="primary-button" onClick={() => { void reconcileSession() }}>Refresh session</button>
    </div>
  }

  return (
    <WorkflowApp
      session={session}
      messages={messages}
      busy={busy}
      error={error}
      onSendMessage={async (message) => {
        setMessages((current) => [...current, { role: 'user', text: message }])
        setBusy(true)
        setError(null)
        try {
          const response = await api.sendMessage(session.session_id, message)
          setMessages((current) => [...current, { role: 'assistant', text: response.message }])
          setSession(response.session)
        } catch (reason) {
          setError(errorMessage(reason))
          await reconcileSession()
        } finally {
          setBusy(false)
        }
      }}
      onConfirmProfile={() => run(() => api.confirmProfile(session.session_id))}
      onProposeResumeEntries={() => run(() => api.proposeResumeEntries(session.session_id))}
      onEditResumeEntry={async (entryId, edit) => {
        let savedEntry: ResumeEntry | undefined
        await run(async () => {
          const updated = await api.updateResumeEntry(session.session_id, entryId, edit)
          savedEntry = updated.resume_entries.find((entry) => entry.entry_id === entryId)
          return updated
        })
        return savedEntry
      }}
      onApproveResumeEntry={(entryId) => run(() => api.approveResumeEntry(session.session_id, entryId))}
      onDeleteResumeEntry={(entryId) => run(() => api.deleteResumeEntry(session.session_id, entryId))}
      onRetrieveJobs={() => run(() => api.retrieveJobs(session.session_id))}
      onSelectJob={(documentId) => run(() => api.selectJob(session.session_id, documentId))}
      onGenerateCV={async () => {
        setBusy(true)
        setError(null)
        try {
          const response = await api.generateCV(session.session_id)
          setSession(response.session)
        } catch (reason) {
          setError(errorMessage(reason))
          await reconcileSession()
        } finally {
          setBusy(false)
        }
      }}
      onSaveCV={(cv) => run(() => api.saveCV(session.session_id, cv))}
      onValidateCV={(cvId) => run(() => api.validateCV(session.session_id, cvId))}
      onRecordExport={(cvId) => run(() => api.recordExport(session.session_id, cvId), true)}
    />
  )
}

function errorMessage(reason: unknown): string {
  if (reason instanceof ApiError) {
    const missing = reason.details.missing_fields
    if (Array.isArray(missing)) {
      return `${reason.message} Missing: ${missing.join(', ').replaceAll('_', ' ')}.`
    }
    return reason.message
  }
  return 'The app could not reach the local API. Check that FastAPI is running and try again.'
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
      <path d="M12 3 4.5 6v5.6c0 4.5 3.2 7.8 7.5 9.4 4.3-1.6 7.5-4.9 7.5-9.4V6L12 3Zm-3 9 2 2 4-5" />
    </svg>
  )
}
