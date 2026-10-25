import { useState, type FormEvent } from 'react'
import Markdown from 'react-markdown'

import type { ChatMessage, Session } from '../types'

interface ProfileStageProps {
  session: Session
  messages: ChatMessage[]
  busy: boolean
  onSendMessage: (message: string) => Promise<void>
  onConfirm: () => Promise<void>
}

export function ProfileStage({
  session,
  messages,
  busy,
  onSendMessage,
  onConfirm,
}: ProfileStageProps) {
  const [message, setMessage] = useState('')
  const profileConfirmed = session.profile.facts.length > 0 &&
    session.profile.facts.every((fact) => fact.status === 'confirmed')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = message.trim()
    if (!value) return
    setMessage('')
    await onSendMessage(value)
  }

  return (
    <section className="stage-panel" aria-labelledby="profile-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Profile</p>
          <h2 id="profile-title">Build your evidence profile</h2>
        </div>
        <span className={`status-pill ${profileConfirmed ? 'success' : ''}`}>
          {profileConfirmed ? 'Confirmed' : session.profile.facts.length ? 'Ready for your review' : 'Getting started'}
        </span>
      </div>
      <p className="section-copy">
        Start with what you know. We’ll help organise the details, and you’ll review
        everything before it becomes part of your CV.
      </p>

      <div className="profile-layout">
        <div className="conversation-card">
          <div className="conversation-heading"><span className="eyebrow">The introduction</span><span>In your own words</span></div>
          <div className="conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="conversation-welcome">
                <h3>Let’s start with you.</h3>
                <p>A degree you’re working towards. A project you’re proud of.
                  The kind of work you’d like to do. There’s no perfect way to start.</p>
                <div className="writing-prompts"><span>Your studies</span><span>Skills & projects</span><span>Your next role</span></div>
              </div>
            ) : (
              messages.map((entry, index) => (
                <div className={`${entry.role}-message`} key={`${entry.role}-${index}`}>
                  <span>{entry.role === 'assistant' ? 'CV guide' : 'You'}</span>
                  {entry.role === 'assistant' ? (
                    <div className="guide-message-content">
                      <Markdown skipHtml allowedElements={[
                        'p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'code', 'a', 'blockquote',
                      ]} unwrapDisallowed>{entry.text}</Markdown>
                    </div>
                  ) : <p>{entry.text}</p>}
                </div>
              ))
            )}
          </div>
          <form onSubmit={submit} className="message-form">
            <label htmlFor="profile-message">Add or correct profile information</label>
            <textarea
              id="profile-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="I’m studying… Recently, I worked on… I’d love a role in…"
              rows={5}
              disabled={busy}
            />
            <div className="composer-footer"><span>You can add or change details along the way.</span>
              <button className="primary-button" type="submit" disabled={busy || !message.trim()}>
                Add to profile <span aria-hidden="true">↗</span>
              </button>
            </div>
          </form>
        </div>

        <aside className="facts-card" aria-label="Profile facts">
          <div className="card-heading">
            <h3>Your profile, taking shape</h3>
            <span>{session.profile.facts.length}</span>
          </div>
          {session.profile.facts.length === 0 ? (
            <div className="profile-empty">
              <svg viewBox="0 0 48 56" width="40" height="48" fill="none" aria-hidden="true"><path d="M8 3h23l10 10v40H8zM31 3v12h10M16 25h17M16 33h17M16 41h10" stroke="currentColor" strokeWidth="1.4" /></svg>
              <p>The details that make you, you.</p>
              <span>Your introduction will become a set of facts here. Check them, make changes, then confirm when they look right.</span>
              <div className="profile-outline"><span>Education</span><span>Experience</span><span>Skills & projects</span></div>
            </div>
          ) : (
            <ul className="fact-list">
              {session.profile.facts.map((fact) => (
                <li key={fact.fact_id}>
                  <div>
                    <span className="fact-field">{fact.field.replaceAll('_', ' ')}</span>
                    <span className={`fact-status ${fact.status}`}>{fact.status}</span>
                  </div>
                  <p>{fact.value}</p>
                  <small>Source: {sourceLabel(fact.source.source_type)}</small>
                </li>
              ))}
            </ul>
          )}
          {session.state === 'profile_review' ? (
            <button className="secondary-button full-width" onClick={onConfirm} disabled={busy}>
              Confirm these facts
            </button>
          ) : null}
          <p className="facts-footnote">Only the details you confirm will be used in your CV.</p>
        </aside>
      </div>
    </section>
  )
}

function sourceLabel(sourceType: string) {
  switch (sourceType) {
    case 'user_message':
      return 'Your message'
    case 'manual_edit':
      return 'Your edit'
    case 'imported_test_profile':
      return 'Imported profile'
    default:
      return 'Profile evidence'
  }
}
