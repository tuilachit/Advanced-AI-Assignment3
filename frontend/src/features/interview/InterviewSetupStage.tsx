import { useState } from 'react'
import type { Session } from '../../types'
import { LiveInterviewStage } from './live/LiveInterviewStage'
import { InterviewFeedback } from './feedback/InterviewFeedback'
import { InterviewSetupForm } from './InterviewSetupForm'
import { interviewReadiness } from './setup'
import { useInterviewSetup } from './useInterviewSetup'
import './interview.css'

interface InterviewSetupStageProps {
  session: Session
  busy: boolean
  visible?: boolean
  onReviewProfile: () => void
  onReviewEntries: () => void
  onReviewJobs: () => void
}

export function InterviewSetupStage({ session, busy, visible = true, onReviewProfile, onReviewEntries, onReviewJobs }: InterviewSetupStageProps) {
  const [view, setView] = useState<'setup' | 'live' | 'feedback'>('setup')
  const setup = useInterviewSetup(session)
  const readiness = interviewReadiness(session)
  const interview = setup.interview

  if (interview && view === 'feedback') return <InterviewFeedback key={interview.interview_id} interview={interview} visible={visible}
    onBack={() => setView('live')} onSetup={() => setView('setup')} />
  if (interview && view === 'live') return <LiveInterviewStage key={interview.interview_id} interview={interview} visible={visible}
    onClose={(updated) => { setup.updateInterview(updated); setView('setup') }}
    onFeedback={(updated) => { setup.updateInterview(updated); setView('feedback') }} />

  return (
    <section className="stage-panel interview-stage" aria-labelledby="interview-title">
      <div className="section-heading">
        <div><p className="eyebrow">Interview practice</p><h2 id="interview-title">Prepare for your next conversation</h2></div>
        <span className="status-pill">Microphone off</span>
      </div>
      <p className="section-copy">Bring your experience and a role you’re interested in. We’ll prepare questions around the facts you’ve confirmed.</p>
      {interview ? (
        <div className="interview-ready-card" role="status">
          <span className="status-pill success">{interview.phase === 'ready' ? 'Interview prepared' : `Interview ${interview.phase}`}</span>
          <h3>{interview.phase === 'ready' ? 'You’re ready to practise for ' : 'Your interview for '}{interview.job.title}</h3>
          <p>{interview.phase === 'ready' ? 'Your questions have been prepared. Your microphone is off and the interview timer has not started.' :
            'Open the interview room to review its current status and transcript. Leaving the room does not pause an active interview.'}</p>
          <dl className="interview-ready-details">
            <div><dt>Focus</dt><dd>{interview.config.interview_type}</dd></div>
            <div><dt>Time limit</dt><dd>{interview.config.duration_minutes} minutes</dd></div>
            <div><dt>Main questions</dt><dd>{interview.questions.filter((question) => question.kind === 'main').length}</dd></div>
            <div><dt>Context</dt><dd>{interview.cv_id ? 'Profile, resume entries & CV' : 'Profile & resume entries'}</dd></div>
          </dl>
          {setup.contextChanged ? <p className="interview-notice">Your CV Builder context has changed. This interview keeps its original information. Prepare another interview to use your latest changes.</p> : null}
          <div className="interview-ready-actions">
            <button className="primary-button" type="button" onClick={() => setView('live')} disabled={busy}>Open interview room</button>
            {interview.phase === 'completed' ? <button className="secondary-button" type="button" onClick={() => setView('feedback')} disabled={busy}>View feedback</button> : null}
            <button className="secondary-button" type="button" onClick={setup.prepareAnother}
              disabled={busy || ['active', 'finalizing'].includes(interview.phase)}>Set up another interview</button>
          </div>
        </div>
      ) : (
        <div className="interview-setup-layout">
          <InterviewSetupForm session={session} form={setup.form} busy={busy}
            preparing={setup.preparing} error={setup.error} onChange={setup.updateForm} onPrepare={setup.prepare} />
          <aside className="interview-context-card" aria-label="Interview preparation checklist">
            <p className="eyebrow">Built on your experience</p>
            <h3>A little preparation.<br /> A clearer conversation.</h3>
            <p>Your confirmed facts and approved resume entries give the interviewer a starting point.</p>
            <ul className="interview-checklist">
              <li>
                <span className={'status-pill ' + (readiness.profileConfirmed ? 'success' : '')}>
                  {readiness.profileConfirmed ? 'Profile confirmed' : 'Confirm your profile'}
                </span>
                <button type="button" className="interview-text-button" disabled={busy || setup.preparing} onClick={onReviewProfile}>Review profile</button>
              </li>
              <li>
                <span className={'status-pill ' + (readiness.approvedEntryCount > 0 ? 'success' : '')}>
                  {readiness.approvedEntryCount > 0
                    ? readiness.approvedEntryCount + (readiness.approvedEntryCount === 1 ? ' approved resume entry' : ' approved resume entries')
                    : 'Approve a resume entry'}
                </span>
                <button type="button" className="interview-text-button" disabled={busy || setup.preparing || !readiness.profileConfirmed} onClick={onReviewEntries}>Review resume entries</button>
              </li>
              <li>
                <span className="status-pill">{readiness.validatedCV ? 'Validated CV available' : 'A CV is optional'}</span>
                <small>You can practise with your profile and approved entries alone.</small>
              </li>
            </ul>
            <button type="button" className="secondary-button" disabled={busy || setup.preparing || !readiness.eligible} onClick={onReviewJobs}>Review job matches</button>
            <p className="interview-context-note">Each interview keeps a snapshot of your information. Later CV edits won’t change questions you’ve already prepared.</p>
          </aside>
        </div>
      )}
    </section>
  )
}
