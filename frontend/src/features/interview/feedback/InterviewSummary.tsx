import type { Interview } from '../../../types'

export function displayDate(value: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Not available'
  return new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function InterviewSummary({ interview }: { interview: Interview }) {
  const main = interview.questions.filter((question) => question.kind === 'main')
  const asked = main.filter((question) => question.status !== 'planned').length
  const answered = main.filter((question) => question.status === 'answered').length
  const skipped = main.filter((question) => question.status === 'skipped').length
  const followUps = interview.questions.filter((question) => question.kind === 'follow_up' && question.status !== 'planned').length
  const elapsed = interview.started_at && interview.ended_at ? Date.parse(interview.ended_at) - Date.parse(interview.started_at) : NaN
  const duration = Number.isFinite(elapsed) && elapsed >= 0
    ? `${Math.floor(elapsed / 60_000)} min ${Math.floor(elapsed / 1000) % 60} sec` : 'Not available'
  const reasons: Record<NonNullable<Interview['end_reason']>, string> = {
    user_finished: 'Ended by you', time_limit: 'Time limit reached', questions_complete: 'Questions complete',
    user_cancelled: 'Cancelled', provider_failure: 'Provider error',
  }
  return <section className="feedback-summary" aria-labelledby="feedback-summary-title">
    <div className="feedback-summary-heading"><div><p className="eyebrow">Interview summary</p>
      <h3 id="feedback-summary-title">{interview.job.title}</h3>
      <p className="feedback-focus">{interview.config.interview_type} interview · {interview.config.duration_minutes}-minute time limit</p></div>
      <span className={'status-pill ' + (interview.phase === 'completed' ? 'success' : '')}>{interview.phase === 'completed' ? 'Completed' : interview.phase}</span>
    </div>
    <dl className="feedback-summary-stats">
      <div><dt>Finished</dt><dd>{displayDate(interview.ended_at)}</dd><small>{interview.end_reason ? reasons[interview.end_reason] : 'Not finished yet'}</small></div>
      <div><dt>Elapsed time</dt><dd>{duration}</dd><small>From interview start to end</small></div>
      <div><dt>Main questions answered</dt><dd>{answered} of {asked} asked</dd><small>{skipped} skipped · {main.length - asked} not asked</small></div>
      <div><dt>Follow-up questions</dt><dd>{followUps} asked</dd><small>Reviewed with their own answers</small></div>
    </dl>
  </section>
}
