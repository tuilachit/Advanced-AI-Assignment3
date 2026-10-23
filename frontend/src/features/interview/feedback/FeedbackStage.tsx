import { useState } from 'react'

import type { Interview } from '../../../types'
import { InterviewSummary, displayDate } from './InterviewSummary'
import { QuestionFeedbackCard } from './QuestionFeedbackCard'
import { TranscriptEvidence } from './TranscriptEvidence'
import { scoreAnchors, type FeedbackSource } from './feedbackView'
import { useFeedback } from './useFeedback'
import './feedback.css'

export interface FeedbackStageProps {
  interview: Interview
  source: FeedbackSource | null
  onBack: () => void
  backLabel?: string
  onSetup?: () => void
  onViewSample?: () => void
}

export function FeedbackStage({ interview, source, onBack, backLabel = 'Back to interview', onSetup, onViewSample }: FeedbackStageProps) {
  const { state, retry } = useFeedback(interview, source)
  const [selection, setSelection] = useState<{ turnId: string } | null>(null)
  const completed = interview.phase === 'completed'
  const report = completed && source && state.status === 'ready' ? state.report : null
  const asked = interview.questions.filter((question) => question.status !== 'planned')
  const notAsked = interview.questions.filter((question) => question.status === 'planned')
  return <section className="stage-panel feedback-stage" aria-labelledby="feedback-title">
    {source?.kind === 'sample' ? <div className="feedback-sample-notice" role="note"><strong>Sample feedback · mock data</strong>
      <p>This is a separate synthetic interview with illustrative scores and metrics. It does not assess your conversation or update your CV.</p></div> : null}
    <div className="section-heading"><div><p className="eyebrow">Interview feedback</p><h2 id="feedback-title">Turn practice into progress</h2></div>
      <div className="feedback-navigation"><button type="button" className="interview-text-button" onClick={onBack}>{backLabel}</button>
        {onSetup ? <button type="button" className="secondary-button" onClick={onSetup}>Back to setup</button> : null}</div></div>
    <p className="section-copy">Review each answer, see the evidence, and choose one thing to practise next.</p>
    <InterviewSummary interview={interview} />

    {!completed ? <div className="feedback-state-card" role="status"><h3>Feedback needs a completed interview</h3>
      <p>{interview.phase === 'finalizing' ? 'The transcript is still finishing. Return to the interview room and wait for completion.'
        : 'This interview has not completed. No assessment has been requested.'}</p></div>
      : !source ? <div className="feedback-state-card" role="status"><h3>Feedback is not connected yet</h3>
        <p>Your interview summary is available above. Automated feedback will be available when the feedback service is connected.</p>
        {onViewSample ? <><p>You can explore a separate example report to see the feedback layout.</p>
          <button type="button" className="primary-button" onClick={onViewSample}>View sample feedback</button></> : null}</div>
      : state.status === 'loading' ? <div className="feedback-state-card" role="status" aria-live="polite" aria-busy="true">
        <span className="feedback-loading-mark" aria-hidden="true" /><h3>{source.kind === 'sample' ? 'Loading sample feedback…' : 'Preparing your feedback…'}</h3>
        <p>{source.kind === 'sample' ? 'Loading the example’s criteria, transcript evidence and speaking metrics.' : 'Checking each answer and its supporting transcript evidence. This may take a moment.'}</p></div>
      : state.status === 'error' ? <div className="feedback-state-card feedback-load-error" role="alert"><h3>Feedback could not be displayed</h3><p>{state.message}</p>
        <button type="button" className="primary-button" onClick={() => void retry()}>Retry feedback</button></div> : null}

    {report ? <>
      <section className="feedback-review-heading" aria-labelledby="feedback-answers-title"><div><p className="eyebrow">One answer at a time</p>
        <h3 id="feedback-answers-title">Question-by-question feedback</h3><p>Scores describe individual criteria on a 0–4 scale. STAR covers Situation, Task, Action and Result as one criterion.</p></div>
        <details className="feedback-rubric"><summary>How to read the scores</summary><ol start={0}>{scoreAnchors.map((anchor, index) => <li key={anchor}><strong>{index}</strong><span>{anchor}</span></li>)}</ol>
          <p><strong>Not applicable:</strong> the criterion does not apply to this question.</p>
          <p><strong>Insufficient evidence:</strong> there is no usable answer to assess. No score is assigned.</p></details></section>
      {asked.length ? <div className="feedback-questions">{asked.map((question, index) => <QuestionFeedbackCard key={question.question_id}
        question={question} interview={interview} review={report.questions.find((item) => item.questionId === question.question_id)} initiallyOpen={index === 0}
        onEvidence={(turnId) => setSelection({ turnId })} />)}</div>
        : <div className="feedback-state-card"><h3>No questions were available to review</h3><p>This interview ended before any questions were issued. There are no criterion scores or speaking metrics to display.</p></div>}
      {notAsked.length ? <section className="feedback-not-asked"><h3>Not asked in this interview</h3><p>These planned questions have no assessment.</p>
        <ul>{notAsked.map((question) => <li key={question.question_id}>{question.text}</li>)}</ul></section> : null}
      <TranscriptEvidence interview={interview} selection={selection} />
      <section className="feedback-limitations" aria-labelledby="feedback-limitations-title"><h3 id="feedback-limitations-title">What this feedback can tell you</h3>
        <ul>{report.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
        <p className="feedback-report-meta">{source?.kind === 'sample' ? 'Sample report' : 'Report'} prepared {displayDate(report.createdAt)} · Rubric {report.rubricVersion}</p></section>
    </> : null}
  </section>
}
