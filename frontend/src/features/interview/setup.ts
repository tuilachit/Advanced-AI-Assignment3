import { stateAtLeast } from '../../components/StageNav'
import type { CreateInterviewRequest, InterviewConfig, Session } from '../../types'

// UI editing state only. Request/response contracts come from generated schema aliases.
export interface InterviewSetupFormState {
  jobSource: CreateInterviewRequest['job']['source']
  documentId: string
  jobTitle: string
  jobDescription: string
  config: InterviewConfig
  includeCV: boolean
  consent: CreateInterviewRequest['consent']
}

export function interviewReadiness(session: Session) {
  const profileConfirmed = session.profile.facts.length > 0 &&
    session.profile.facts.every((fact) => fact.status === 'confirmed')
  const approvedEntryCount = session.resume_entries.filter((entry) => entry.status === 'approved').length
  const eligible = profileConfirmed && approvedEntryCount > 0 &&
    stateAtLeast(session.state, 'resume_entries_approved')
  const validatedCV = Boolean(session.cv && session.validated_content_hash &&
    (session.state === 'cv_validated' || session.state === 'pdf_exported'))
  return { profileConfirmed, approvedEntryCount, eligible, validatedCV }
}

export function setupContextKey(session: Session): string {
  return JSON.stringify([
    session.session_id, session.profile.revision, session.resume_entries_revision,
    session.selected_job_id, session.cv?.cv_id, session.validated_content_hash,
  ])
}

export function defaultSetupForm(session: Session): InterviewSetupFormState {
  const job = session.retrieval_results.find((item) => item.document_id === session.selected_job_id) ??
    session.retrieval_results[0]
  return {
    jobSource: job ? 'supplied_job' : 'pasted_job',
    documentId: job?.document_id ?? '',
    jobTitle: '',
    jobDescription: '',
    config: {
      interview_type: 'mixed', duration_minutes: 10, main_question_count: 4,
      max_follow_ups_per_question: 1, language: 'en',
    },
    includeCV: interviewReadiness(session).validatedCV,
    consent: { send_audio_to_provider: false, retain_transcript_for_feedback: false },
  }
}

export function canPrepareInterview(session: Session, form: InterviewSetupFormState): boolean {
  const jobValid = form.jobSource === 'supplied_job'
    ? session.retrieval_results.some((job) => job.document_id === form.documentId)
    : Boolean(form.jobTitle.trim() && form.jobDescription.trim() &&
      form.jobTitle.trim().length <= 200 && form.jobDescription.trim().length <= 20_000)
  return interviewReadiness(session).eligible && jobValid &&
    form.consent.send_audio_to_provider && form.consent.retain_transcript_for_feedback
}

export function interviewPayload(session: Session, form: InterviewSetupFormState): Omit<CreateInterviewRequest, 'request_id'> {
  return {
    job: form.jobSource === 'supplied_job'
      ? { source: 'supplied_job', document_id: form.documentId }
      : { source: 'pasted_job', title: form.jobTitle.trim(), description: form.jobDescription.trim() },
    cv_id: form.includeCV && interviewReadiness(session).validatedCV ? session.cv?.cv_id : null,
    config: form.config,
    consent: form.consent,
  }
}
