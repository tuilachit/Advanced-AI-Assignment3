import type { Interview } from '../../../types'
import { criterionLabels, evidenceTurn, scoreAnchors, type CriterionReview } from './feedbackView'

export function CriteriaFeedback({ criteria, questionId, interview, onEvidence }: {
  criteria: CriterionReview[]; questionId: string; interview: Interview; onEvidence: (turnId: string) => void
}) {
  return <div className="feedback-criteria-grid">{criteria.map((criterion) => {
    const label = criterionLabels[criterion.key]
    const assessed = criterion.rating.kind === 'assessed'
    const evidenceAvailable = criterion.evidence.length > 0 && criterion.evidence.every((reference) => evidenceTurn(interview, questionId, reference))
    const supported = !assessed || evidenceAvailable
    const score = criterion.rating.kind === 'assessed' && evidenceAvailable ? criterion.rating.score : null
    const status = !supported ? 'Evidence unavailable' : criterion.rating.kind === 'notApplicable' ? 'Not applicable' : 'Insufficient evidence'
    return <section className="feedback-criterion" key={criterion.key} aria-label={label + ' evaluation'}>
      <div className="feedback-criterion-heading"><h4>{label}</h4>
        {score !== null ? <span className="feedback-score" aria-label={`${label}: ${score} of 4 — ${scoreAnchors[score]}`}>
          <strong>{score}</strong><span> / 4</span></span> : <span className="feedback-unrated">{status}</span>}
      </div>
      {criterion.key === 'star' ? <p className="feedback-star-key">Situation · Task · Action · Result</p> : null}
      <p>{supported ? criterion.explanation : 'The cited final answer could not be found in this interview. This assessment cannot be displayed with supporting evidence.'}</p>
      {supported ? criterion.evidence.map((reference, index) => <figure className="feedback-quote" key={reference.turnId + ':' + index}>
        <blockquote>{reference.excerpt}</blockquote><figcaption>Candidate transcript
          <button className="interview-text-button" type="button" onClick={() => onEvidence(reference.turnId)}>View full answer</button></figcaption>
      </figure>) : null}
      {supported && criterion.suggestion ? <div className="feedback-suggestion"><strong>Try next time</strong><p>{criterion.suggestion}</p></div> : null}
    </section>
  })}</div>
}
