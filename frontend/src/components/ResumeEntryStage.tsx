import { useId, useState } from 'react'

import type { ResumeEntry, ResumeEntryEdit, Session } from '../types'

interface ResumeEntryStageProps {
  session: Session
  busy: boolean
  onPropose: () => Promise<void>
  onEdit: (entryId: string, edit: ResumeEntryEdit) => Promise<ResumeEntry | void>
  onApprove: (entryId: string) => Promise<void>
  onDelete: (entryId: string) => Promise<void>
}

const kindLabels: Record<ResumeEntry['kind'], string> = {
  experience: 'Experience', project: 'Project', education: 'Education',
  skills: 'Skills', achievement: 'Achievement',
}

const statusLabels: Record<ResumeEntry['status'], string> = {
  proposed: 'Proposed', approved: 'Approved', needs_review: 'Needs review',
}

export function ResumeEntryStage(props: ResumeEntryStageProps) {
  const { session, busy, onPropose } = props
  return (
    <section className="stage-panel" aria-labelledby="resume-title">
      <div className="section-heading">
        <h2 id="resume-title">Review your resume entries</h2>
      </div>
      <p className="section-copy">
        Check the wording against your experience, then approve each entry you want to use.
        Approve at least one experience, project, education or achievement entry to unlock Job matches.
      </p>
      {session.resume_entries.length === 0 ? (
        <div className="action-card">
          <h3>Turn your confirmed facts into CV-ready entries</h3>
          <p>We will structure what you told us. Review every entry before it can appear in your CV.</p>
          <button className="primary-button" onClick={onPropose} disabled={busy}>Create resume entries</button>
        </div>
      ) : (
        <div className="resume-entry-grid">
          {session.resume_entries.map((entry) => (
            <ResumeEntryCard
              {...props}
              entry={entry}
              // Reset a draft only when this entry changes on the server, including after reconciliation.
              key={JSON.stringify(entry)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function displayEdit(entry: ResumeEntry): ResumeEntryEdit {
  return {
    heading: entry.heading.text,
    organisation_or_context: entry.organisation_or_context?.text ?? null,
    details: entry.details.map((detail) => detail.value.text),
    bullets: entry.bullets.map((bullet) => bullet.text),
  }
}

function ResumeEntryCard({ entry, session, busy, onEdit, onApprove, onDelete }:
  ResumeEntryStageProps & { entry: ResumeEntry }) {
  const id = useId()
  const [draft, setDraft] = useState(() => displayEdit(entry))
  const dirty = JSON.stringify(draft) !== JSON.stringify(displayEdit(entry))
  const emptyText = [draft.heading, ...(draft.details ?? []), ...(draft.bullets ?? []),
    ...(draft.organisation_or_context === null ? [] : [draft.organisation_or_context ?? '']),
  ].some((text) => !text.trim())
  const sources = entry.source_fact_ids.map((factId) => session.profile.facts.find((fact) => fact.fact_id === factId))
  const sourcesConfirmed = sources.length > 0 && sources.every((fact) => fact?.status === 'confirmed')

  return (
    <article className="resume-entry-card" aria-labelledby={`${id}-title`}>
      <div className="entry-card-heading">
        <span className="eyebrow">{kindLabels[entry.kind]}</span>
        <span className={`entry-status ${entry.status}`}>{statusLabels[entry.status]}</span>
      </div>
      <div className="entry-preview">
        <h3 id={`${id}-title`}>{draft.heading}</h3>
        {draft.organisation_or_context !== null ? <p>{draft.organisation_or_context}</p> : null}
        {entry.details.length > 0 ? <dl>{entry.details.map((detail, index) => (
          <div key={index}><dt>{detail.label}</dt><dd>{draft.details?.[index]}</dd></div>
        ))}</dl> : null}
        {draft.bullets?.length ? <ul>{draft.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}</ul> : null}
      </div>
      <div className="entry-source-list">
        <h4>Based on what you told us</h4>
        <ul>{sources.map((fact, index) => <li key={index}>
          {fact?.value ?? 'This source is no longer in your profile.'}
        </li>)}</ul>
      </div>
      {!sourcesConfirmed ? <p className="editor-help">Confirm the source facts in Profile before approving this entry.</p> : null}
      {entry.status === 'needs_review' ? (
        <p className="editor-help">Review the wording against your confirmed facts, save any changes, then approve this entry again.</p>
      ) : null}
      <form className="entry-editor" onSubmit={async (event) => {
        event.preventDefault()
        if (!busy && dirty && !emptyText) {
          const savedEntry = await onEdit(entry.entry_id, draft)
          // A successful save can normalize whitespace without changing the card key.
          if (savedEntry) setDraft(displayEdit(savedEntry))
        }
      }}>
        <label htmlFor={`${id}-heading`}>Heading</label>
        <input id={`${id}-heading`} value={draft.heading} disabled={busy}
          onChange={(event) => setDraft({ ...draft, heading: event.target.value })} />
        {entry.organisation_or_context !== null ? <>
          <label htmlFor={`${id}-context`}>Organisation or context</label>
          <input id={`${id}-context`} value={draft.organisation_or_context ?? ''} disabled={busy}
            onChange={(event) => setDraft({ ...draft, organisation_or_context: event.target.value })} />
        </> : null}
        {entry.details.map((detail, index) => <div className="entry-field" key={index}>
          <label htmlFor={`${id}-detail-${index}`}>{detail.label}</label>
          <input id={`${id}-detail-${index}`} value={draft.details?.[index] ?? ''} disabled={busy}
            onChange={(event) => setDraft({ ...draft, details: draft.details?.map((value, i) => i === index ? event.target.value : value) })} />
        </div>)}
        {draft.bullets?.map((bullet, index) => <div className="entry-field" key={index}>
          <label htmlFor={`${id}-bullet-${index}`}>Bullet {index + 1}</label>
          <textarea id={`${id}-bullet-${index}`} rows={3} value={bullet} disabled={busy}
            onChange={(event) => setDraft({ ...draft, bullets: draft.bullets?.map((value, i) => i === index ? event.target.value : value) })} />
        </div>)}
        {dirty ? <p className="editor-help">Save your changes before approving this entry.</p> : null}
        <div className="entry-actions">
          <button className="secondary-button" type="submit" disabled={busy || !dirty || emptyText}>Save changes</button>
          <button className="primary-button" type="button" disabled={busy || dirty || !sourcesConfirmed || entry.status === 'approved'}
            onClick={() => onApprove(entry.entry_id)}>Approve entry</button>
          <button className="secondary-button" type="button" disabled={busy}
            onClick={() => onDelete(entry.entry_id)}>Remove entry</button>
        </div>
      </form>
    </article>
  )
}
