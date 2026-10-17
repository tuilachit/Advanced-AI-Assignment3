import type { Session } from '../types'

export function EvidenceStage({ session }: { session: Session }) {
  const facts = new Map(session.profile.facts.map((fact) => [fact.fact_id, fact]))
  const entryTrace = session.trace.filter((event) =>
    event.event_type.startsWith('resume_entry_') || event.event_type.startsWith('resume_entries_'))
  const claims = [
    ...(session.cv ? [{ claim_id: 'headline', text: session.cv.headline,
      fact_ids: session.cv.headline_fact_ids ?? [] }] : []),
    ...(session.cv?.claims ?? []),
    ...(session.cv?.sections.flatMap((section) => section.claims) ?? []),
  ]

  return (
    <section className="stage-panel" aria-labelledby="evidence-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Evidence</p>
          <h2 id="evidence-title">See why every output exists</h2>
        </div>
        <span className="status-pill">Session trace</span>
      </div>
      <p className="section-copy">
        This view separates profile evidence, job evidence and model actions so the result can be
        inspected rather than trusted blindly.
      </p>

      <div className="evidence-grid">
        <article className="evidence-card">
          <h3>Profile facts</h3>
          {session.profile.facts.length ? (
            <ul className="evidence-list">
              {session.profile.facts.map((fact) => (
                <li key={fact.fact_id}>
                  <strong>{fact.field.replaceAll('_', ' ')}</strong>
                  <p>{fact.field}: {fact.value}</p>
                  <small>
                    ID {fact.fact_id} · Status: {fact.status} · <span>Source: {fact.source.reference}</span>
                  </small>
                </li>
              ))}
            </ul>
          ) : <p className="empty-copy">No profile evidence yet.</p>}
        </article>

        <article className="evidence-card">
          <h3>Resume entry map</h3>
          {session.resume_entries.length ? (
            <ul className="evidence-list">
              {session.resume_entries.map((entry) => {
                const textItems = [
                  { label: 'Heading', value: entry.heading },
                  ...(entry.organisation_or_context
                    ? [{ label: 'Organisation or context', value: entry.organisation_or_context }] : []),
                  ...entry.details,
                  ...entry.bullets.map((value, index) => ({ label: `Bullet ${index + 1}`, value })),
                ]
                return <li key={entry.entry_id}>
                  <small>ID {entry.entry_id} · {entry.kind} · Status: {entry.status.replaceAll('_', ' ')}</small>
                  <dl>{textItems.map(({ label, value }, index) => <div key={index}>
                    <dt>{label}</dt>
                    <dd>
                      <p>{value.text}</p>
                      <div className="evidence-chips">
                        {value.fact_ids.map((factId) => <span key={factId}>{factId}</span>)}
                      </div>
                    </dd>
                  </div>)}</dl>
                  <p>Source facts</p>
                  <ul>
                    {entry.source_fact_ids.map((factId) => <li key={factId}>
                      {factId}: {facts.get(factId)?.value ?? 'Source fact is unavailable.'}
                    </li>)}
                  </ul>
                  {session.resume_entry_validation_issues.filter((issue) => issue.entry_id === entry.entry_id)
                    .map((issue) => <p key={issue.issue_id} className={`issue-${issue.severity}`}>
                      {issue.severity}: {issue.message}
                    </p>)}
                </li>
              })}
            </ul>
          ) : <p className="empty-copy">Create resume entries to see their source mappings.</p>}
          <h4>Entry review history</h4>
          {entryTrace.length ? <ol className="timeline">
            {entryTrace.map((event) => <li key={event.event_id}>
              <time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit',
              })}</time>
              <div>
                <strong>{event.event_type.replaceAll('_', ' ')}</strong>
                <p>{event.summary}</p>
                <small>{JSON.stringify(event.details)}</small>
              </div>
            </li>)}
          </ol> : <p className="empty-copy">No resume entry review events yet.</p>}
        </article>

        <article className="evidence-card">
          <h3>CV claim map</h3>
          {claims.length ? (
            <ul className="evidence-list">
              {claims.map((claim) => (
                <li key={claim.claim_id}>
                  <p>{claim.text}</p>
                  <div className="evidence-chips">
                    {claim.fact_ids.map((factId) => (
                      <span key={factId} title={facts.get(factId)?.value}>{factId}</span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="empty-copy">Generate a CV to see claim mappings.</p>}
        </article>

        <article className="evidence-card full-span">
          <h3>Job-ranking audit</h3>
          {session.retrieval_results.length ? (
            <ul className="evidence-list ranking-audit">
              {session.retrieval_results.map((job, index) => (
                <li key={job.document_id}>
                  <strong>Match {index + 1}: {job.title}</strong>
                  <small>Job record ID: {job.document_id}</small>
                  <p>Final relevance score: {job.score_breakdown.final_score.toFixed(3)}</p>
                  <dl>
                    <div><dt>Broad semantic similarity</dt><dd>{job.score_breakdown.semantic_score.toFixed(3)}</dd></div>
                    <div><dt>Confirmed project evidence</dt><dd>{job.score_breakdown.project_score.toFixed(3)}</dd></div>
                    <div><dt>Confirmed skills evidence</dt><dd>{job.score_breakdown.skill_score.toFixed(3)}</dd></div>
                    <div><dt>Target role, education and experience</dt><dd>{job.score_breakdown.target_role_score.toFixed(3)} / {job.score_breakdown.education_score.toFixed(3)} / {job.score_breakdown.experience_score.toFixed(3)}</dd></div>
                  </dl>
                </li>
              ))}
            </ul>
          ) : <p className="empty-copy">Retrieve jobs to inspect the ranking audit.</p>}
        </article>

        <article className="evidence-card full-span">
          <h3>Tool and decision trace</h3>
          {session.trace.length ? (
            <ol className="timeline">
              {session.trace.map((event) => (
                <li key={event.event_id}>
                  <time dateTime={event.timestamp}>
                    {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </time>
                  <div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.summary}</p></div>
                </li>
              ))}
            </ol>
          ) : <p className="empty-copy">No events recorded yet.</p>}
        </article>
      </div>
    </section>
  )
}
