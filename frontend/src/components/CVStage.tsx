import { lazy, Suspense, useEffect, useState } from 'react'

import type { CVClaim, CVDocument, Fact, Session } from '../types'

const PDFExportPanel = lazy(() => import('./PDFExportPanel'))

interface CVStageProps {
  session: Session
  busy: boolean
  onGenerate: () => Promise<void>
  onSave: (cv: CVDocument) => Promise<void>
  onValidate: (cvId: string) => Promise<void>
  onRecordExport: (cvId: string) => Promise<void>
}

export function CVStage({
  session,
  busy,
  onGenerate,
  onSave,
  onValidate,
  onRecordExport,
}: CVStageProps) {
  const [draft, setDraft] = useState<CVDocument | null>(session.cv)

  useEffect(() => {
    setDraft(session.cv)
  }, [session.cv])

  if (!draft) {
    return (
      <section className="stage-panel" aria-labelledby="cv-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CV studio</p>
            <h2 id="cv-title">Create a job-specific CV</h2>
          </div>
        </div>
        <div className="action-card">
          <h3>Your selected job is ready</h3>
          <p>Your CV is tailored to this job using your approved resume entries and confirmed contact information. Every statement remains linked to the facts you confirmed.</p>
          <button className="primary-button" onClick={onGenerate} disabled={busy}>
            Generate evidence-backed CV
          </button>
        </div>
      </section>
    )
  }

  const unsaved = JSON.stringify(draft) !== JSON.stringify(session.cv)
  const exportReady =
    !unsaved &&
    Boolean(session.validated_content_hash) &&
    (session.state === 'cv_validated' || session.state === 'pdf_exported')
  const factsById = new Map(session.profile.facts.map((fact) => [fact.fact_id, fact]))
  const targetJobTitle = session.retrieval_results.find(
    (job) => job.document_id === session.selected_job_id,
  )?.title
  const contactFields = new Set(['name', 'email', 'phone', 'github', 'linkedin'])
  const contactClaims = draft.claims
    .map((claim, index) => ({ claim, index }))
    .filter(({ claim }) => isContactClaim(claim, factsById, contactFields))
  const profileClaims = draft.claims
    .map((claim, index) => ({ claim, index }))
    .filter(({ claim }) => !isContactClaim(claim, factsById, contactFields))

  function renderClaim(claim: CVClaim, index: number, label: string, sectionIndex?: number) {
    if (!draft) return null
    return <div className="claim-editor" key={claim.claim_id}>
      <label htmlFor={`claim-${claim.claim_id}`}>{label}</label>
      <textarea id={`claim-${claim.claim_id}`} value={claim.text} rows={3}
        onChange={(event) => {
          const edited = { ...claim, text: event.target.value, verified: false }
          if (sectionIndex === undefined) {
            setDraft({ ...draft, claims: draft.claims.map((current, i) => i === index ? edited : current) })
          } else {
            setDraft({ ...draft, sections: draft.sections.map((section, i) => i === sectionIndex
              ? { ...section, claims: section.claims.map((current, j) => j === index ? edited : current) }
              : section) })
          }
        }} />
      <small>{supportText(claim.fact_ids, factsById)}</small>
    </div>
  }

  return (
    <section className="stage-panel" aria-labelledby="cv-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">CV studio</p>
          <h2 id="cv-title">Shape and verify your CV</h2>
        </div>
        <span className={`status-pill ${exportReady ? 'success' : ''}`}>
          {exportReady ? 'Evidence validated' : 'Draft'}
        </span>
      </div>
      <div className="cv-layout">
        <div className="editor-card">
          <label htmlFor="cv-headline">Professional headline</label>
          <textarea
            id="cv-headline"
            className="headline-input"
            value={draft.headline}
            rows={2}
            onChange={(event) =>
              setDraft({ ...draft, headline: event.target.value.replace(/[\r\n]+/g, ' ') })
            }
          />
          <small>{supportText(draft.headline_fact_ids ?? [], factsById)}</small>
          <h3>Your CV statements</h3>
          <p className="editor-help">Every statement must be supported by information you confirmed. Edit anything that is inaccurate, then validate again.</p>
          {contactClaims.length ? <section>
            <h3>Contact details</h3>
            {contactClaims.map(({ claim, index }, displayIndex) => renderClaim(claim, index, `Contact detail ${displayIndex + 1}`))}
          </section> : null}
          {profileClaims.length ? <section>
            <h3>Profile statements</h3>
            {profileClaims.map(({ claim, index }, displayIndex) => renderClaim(claim, index, `Profile statement ${displayIndex + 1}`))}
          </section> : null}
          {draft.sections.map((section, sectionIndex) => <section key={sectionIndex}>
            <h3>{section.heading}</h3>
            {section.claims.map((claim, index) => renderClaim(claim, index, `${section.heading} statement ${index + 1}`, sectionIndex))}
          </section>)}
          <div className="button-row">
            <button
              className="secondary-button"
              disabled={busy || !unsaved}
              onClick={() => onSave(draft)}
            >
              Save changes
            </button>
            <button
              className="primary-button"
              disabled={busy || unsaved}
              onClick={() => onValidate(draft.cv_id)}
            >
              Validate evidence
            </button>
          </div>
        </div>

        <aside className="validation-card">
          <h3>Your PDF</h3>
          {session.validation_issues.length ? (
            <ul className="issue-list">
              {session.validation_issues.map((issue) => (
                <li className={`issue-${issue.severity}`} key={issue.issue_id}>
                  <strong>{issue.severity === 'warning' ? 'Review wording' : 'Change required'}</strong>
                  <p>{issue.message}</p>
                  {issue.severity === 'warning' ? <small>You can reword this statement or keep it after review.</small> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {exportReady ? (
            <Suspense fallback={<p>Preparing local PDF renderer…</p>}>
              <PDFExportPanel
                cv={draft}
                facts={session.profile.facts}
                targetJobTitle={targetJobTitle}
                busy={busy}
                onExport={() => onRecordExport(draft.cv_id)}
              />
            </Suspense>
          ) : (
            <div className="locked-export">
              <LockIcon />
              <p>Validate this exact draft to unlock PDF export.</p>
              {unsaved ? <small>Save your current edits first.</small> : null}
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}

function isContactClaim(
  claim: CVClaim,
  factsById: Map<string, Fact>,
  contactFields: Set<string>,
) {
  const facts = claim.fact_ids.map((factId) => factsById.get(factId)).filter((fact): fact is Fact => Boolean(fact))
  return facts.length > 0 && facts.every((fact) => contactFields.has(fact.field))
}

function supportText(factIds: string[], factsById: Map<string, Fact>) {
  const values = factIds
    .map((factId) => factsById.get(factId))
    .filter((fact): fact is Fact => fact?.status === 'confirmed')
    .map((fact) => fact.value)
  return values.length
    ? `Supported by your confirmed profile: ${values.join(' · ')}`
    : 'No confirmed profile information is linked yet.'
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
      <path d="M7 10V7a5 5 0 0 1 10 0v3m-9 0h8a2 2 0 0 1 2 2v7H6v-7a2 2 0 0 1 2-2Z" />
    </svg>
  )
}
