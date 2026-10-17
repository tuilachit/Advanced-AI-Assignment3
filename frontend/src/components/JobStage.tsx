import type { Session } from '../types'

interface JobStageProps {
  session: Session
  busy: boolean
  onRetrieve: () => Promise<void>
  onSelect: (documentId: string) => Promise<void>
}

export function JobStage({ session, busy, onRetrieve, onSelect }: JobStageProps) {
  return (
    <section className="stage-panel" aria-labelledby="jobs-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Job matches</p>
          <h2 id="jobs-title">Find your strongest matches</h2>
        </div>
        <span className="status-pill">Top 3 of 9 supplied jobs</span>
      </div>
      <p className="section-copy">
        Similarity finds relevant work; eligibility is checked separately. A high match never
        promises that you meet every requirement.
      </p>

      {session.retrieval_results.length === 0 ? (
        <div className="action-card">
          <h3>Ready to search</h3>
          <p>Your confirmed facts become the search query. Your name is excluded.</p>
          <button className="primary-button" onClick={onRetrieve} disabled={busy}>
            Retrieve top 3 jobs
          </button>
        </div>
      ) : (
        <div className="job-grid">
          {session.retrieval_results.map((job, index) => {
            const selected = session.selected_job_id === job.document_id
            return (
              <article className={`job-card ${selected ? 'is-selected' : ''}`} key={job.document_id}>
                <div className="job-rank">Match {index + 1}</div>
                <h3>{job.title}</h3>
                <p className="match-summary">Relevant to your confirmed profile</p>
                <blockquote>{job.excerpt}</blockquote>
                <details className="relevance-breakdown">
                  <summary>Why this appeared</summary>
                  <p>It combines broad relevance with the confirmed projects, skills, education and experience shown below. View detailed scoring in Evidence.</p>
                </details>
                <div className="reason-list">
                  <h4>Confirmed evidence signals</h4>
                  {job.match_reasons.length ? (
                    <ul>{job.match_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  ) : (
                    <p>No source-backed evidence signal was recorded.</p>
                  )}
                </div>
                <div className="job-evidence-grid">
                  <section>
                    <h4>Matched skills</h4>
                    {job.matched_skills.length ? (
                      <div className="skill-chips">
                        {job.matched_skills.map((skill) => <span key={skill}>{skill}</span>)}
                      </div>
                    ) : (
                      <p>No exact skill term matched.</p>
                    )}
                  </section>
                  <section>
                    <h4 aria-label="Missing requirements">Missing requirements <small>Not confirmed in your profile</small></h4>
                    {job.missing_requirements.length ? (
                      <ul>
                        {job.missing_requirements.map((requirement) => (
                          <li key={requirement}>{requirement}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>No unmatched requirement was detected by this evidence check. Review the full job record.</p>
                    )}
                  </section>
                </div>
                <p className="eligibility-note">{job.eligibility_notes[0]}</p>
                <button
                  className={selected ? 'selected-button' : 'secondary-button'}
                  disabled={busy || selected}
                  onClick={() => onSelect(job.document_id)}
                >
                  {selected ? 'Selected' : 'Select this job'}
                </button>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
