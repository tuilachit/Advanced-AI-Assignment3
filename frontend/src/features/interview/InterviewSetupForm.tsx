import type { FormEvent } from 'react'

import type { InterviewConfig, Session } from '../../types'
import { canPrepareInterview, interviewReadiness, type InterviewSetupFormState } from './setup'

interface InterviewSetupFormProps {
  session: Session
  form: InterviewSetupFormState
  busy: boolean
  preparing: boolean
  error: string | null
  onChange: (change: Partial<InterviewSetupFormState>) => void
  onPrepare: () => Promise<void>
}

export function InterviewSetupForm({ session, form, busy, preparing, error, onChange, onPrepare }: InterviewSetupFormProps) {
  const readiness = interviewReadiness(session)
  const disabled = busy || preparing
  const canPrepare = canPrepareInterview(session, form)
  const updateConfig = (change: Partial<InterviewConfig>) => onChange({ config: { ...form.config, ...change } })
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!disabled && canPrepare) void onPrepare()
  }

  return (
    <form className="interview-setup-form" onSubmit={submit} aria-label="Interview setup" aria-busy={preparing}>
      <fieldset className="interview-card" disabled={disabled}>
        <legend><span className="interview-step-number">01</span> Choose your target role</legend>
        <p className="interview-help">Practise for a matched role, or bring a job description of your own.</p>
        <div className="interview-source-options" role="group" aria-label="Job source">
          <label className="interview-choice">
            <input type="radio" name="interview-job-source" value="supplied_job"
              checked={form.jobSource === 'supplied_job'} onChange={() => onChange({ jobSource: 'supplied_job' })} />
            <span>A matched job</span>
          </label>
          <label className="interview-choice">
            <input type="radio" name="interview-job-source" value="pasted_job"
              checked={form.jobSource === 'pasted_job'} onChange={() => onChange({ jobSource: 'pasted_job' })} />
            <span>Paste a job description</span>
          </label>
        </div>
        {form.jobSource === 'supplied_job' ? (
          session.retrieval_results.length ? (
            <div className="interview-field">
              <label htmlFor="interview-job">Target job</label>
              <select id="interview-job" value={form.documentId} required onChange={(event) => onChange({ documentId: event.target.value })}>
                {session.retrieval_results.map((job) => <option key={job.document_id} value={job.document_id}>{job.title}</option>)}
              </select>
              <p className="interview-help">Your selected CV Builder job is prefilled. Choosing a different interview role keeps your CV Builder selection.</p>
            </div>
          ) : <p className="interview-notice">No job matches yet. Retrieve jobs in Job matches, or paste a description here.</p>
        ) : (
          <div className="interview-fields">
            <div className="interview-field">
              <label htmlFor="interview-job-title">Job title</label>
              <input id="interview-job-title" value={form.jobTitle} required maxLength={200}
                placeholder="e.g. Graduate Software Engineer" onChange={(event) => onChange({ jobTitle: event.target.value })} />
            </div>
            <div className="interview-field">
              <label htmlFor="interview-job-description">Job description</label>
              <textarea id="interview-job-description" value={form.jobDescription} required maxLength={20_000}
                rows={6} placeholder="Paste the responsibilities, requirements and skills for the role."
                aria-describedby="interview-description-help" onChange={(event) => onChange({ jobDescription: event.target.value })} />
              <div id="interview-description-help" className="interview-field-note">
                <span>Used to tailor questions. Job requirements do not become facts about you.</span>
                <span>{form.jobDescription.length.toLocaleString()} / 20,000</span>
              </div>
            </div>
          </div>
        )}
      </fieldset>

      <fieldset className="interview-card" disabled={disabled}>
        <legend><span className="interview-step-number">02</span> Make the practice yours</legend>
        <div className="interview-settings-grid">
          <div className="interview-field">
            <label htmlFor="interview-type">Interview focus</label>
            <select id="interview-type" value={form.config.interview_type}
              onChange={(event) => updateConfig({ interview_type: event.target.value as InterviewConfig['interview_type'] })}>
              <option value="mixed">Mixed — behavioural &amp; technical</option>
              <option value="behavioural">Behavioural — your experience</option>
              <option value="technical">Technical — your approach</option>
            </select>
          </div>
          <div className="interview-field">
            <label htmlFor="interview-duration">Time limit</label>
            <select id="interview-duration" value={form.config.duration_minutes}
              onChange={(event) => updateConfig({ duration_minutes: Number(event.target.value) as InterviewConfig['duration_minutes'] })}>
              {[5, 10, 15].map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}
            </select>
          </div>
          <div className="interview-field">
            <label htmlFor="interview-question-count">Main questions</label>
            <select id="interview-question-count" value={form.config.main_question_count}
              onChange={(event) => updateConfig({ main_question_count: Number(event.target.value) })}>
              {[3, 4, 5, 6].map((count) => <option key={count} value={count}>{count} questions</option>)}
            </select>
          </div>
          <div className="interview-field">
            <label htmlFor="interview-follow-ups">Follow-ups per question</label>
            <select id="interview-follow-ups" value={form.config.max_follow_ups_per_question}
              onChange={(event) => updateConfig({ max_follow_ups_per_question: Number(event.target.value) })}>
              <option value={0}>None</option>
              <option value={1}>Up to 1</option>
              <option value={2}>Up to 2</option>
            </select>
          </div>
        </div>
        <p className="interview-help">Questions are in English. The interview may finish sooner if you complete all questions.</p>
        <label className="interview-choice interview-cv-choice">
          <input type="checkbox" checked={readiness.validatedCV && form.includeCV} disabled={!readiness.validatedCV}
            onChange={(event) => onChange({ includeCV: event.target.checked })} />
          <span>Include my current validated CV
            <small>{readiness.validatedCV ? 'Your saved, validated CV can help tailor the questions.' :
              'Optional. Save and validate a CV in CV studio to include it.'}</small>
          </span>
        </label>
      </fieldset>

      <fieldset className="interview-card" disabled={disabled}>
        <legend><span className="interview-step-number">03</span> Your voice, your choice</legend>
        <p className="interview-help">Both choices are required to prepare a voice interview. Your microphone stays off during setup.</p>
        <div className="interview-consent-options">
          <label className="interview-choice">
            <input type="checkbox" required checked={form.consent.send_audio_to_provider}
              onChange={(event) => onChange({ consent: { ...form.consent, send_audio_to_provider: event.target.checked } })} />
            <span>I agree to send my audio to the AI provider during the interview.</span>
          </label>
          <label className="interview-choice">
            <input type="checkbox" required checked={form.consent.retain_transcript_for_feedback}
              onChange={(event) => onChange({ consent: { ...form.consent, retain_transcript_for_feedback: event.target.checked } })} />
            <span>I agree to keep my transcript in this temporary workspace for feedback.</span>
          </label>
        </div>
      </fieldset>

      {error ? <div className="error-banner interview-error" role="alert"><strong>We couldn’t prepare your interview.</strong><p>{error}</p></div> : null}
      <div className="interview-submit-row">
        <div role="status" aria-live="polite">
          {preparing ? <span>Preparing questions from your confirmed experience… This can take a few seconds.</span> :
            !readiness.eligible ? <span>Confirm your profile and approve a resume entry before preparing.</span> :
            !canPrepare ? <span>Add a target role and select both consent choices to continue.</span> :
            <span>Ready to prepare. Your microphone will stay off.</span>}
        </div>
        <button className="primary-button" type="submit" disabled={disabled || !canPrepare}>
          {preparing ? 'Preparing interview…' : error ? 'Try again' : 'Prepare interview'}
        </button>
      </div>
    </form>
  )
}
