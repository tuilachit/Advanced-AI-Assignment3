import { useEffect, useRef, useState } from 'react'
import type { Interview } from '../../../types'
import { questionLabel } from './QuestionFeedbackCard'

export function TranscriptEvidence({ interview, selection }: { interview: Interview; selection: { turnId: string } | null }) {
  const [open, setOpen] = useState(false)
  const panel = useRef<HTMLDetailsElement>(null)
  const target = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (!selection) return
    setOpen(true)
    if (panel.current) panel.current.open = true
    target.current?.focus({ preventScroll: true })
    target.current?.scrollIntoView?.({ block: 'center', behavior: 'auto' })
  }, [selection])

  return <details className="feedback-transcript" ref={panel} open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Transcript evidence <span>{interview.turns.length} {interview.turns.length === 1 ? 'turn' : 'turns'}</span></summary>
    <p className="feedback-help">Quotes link to final candidate answers. Partial or failed transcription cannot support a criterion score.</p>
    {interview.turns.length ? <ol>{interview.turns.map((turn, index) => {
      const question = interview.questions.find((item) => item.question_id === turn.question_id)
      const selected = selection?.turnId === turn.turn_id
      return <li key={turn.turn_id} ref={selected ? target : null} tabIndex={-1} className={selected ? 'is-selected' : ''}>
        <div className="feedback-turn-heading"><strong>{turn.speaker === 'candidate' ? 'Candidate' : 'Interviewer'} · Turn {index + 1}</strong>
          <span>{question ? questionLabel(question, interview) : 'Question unavailable'} · {turn.transcript_status === 'final' ? 'Final transcript'
            : turn.transcript_status === 'failed' ? 'Transcription unavailable' : 'Provisional transcript'}
            {turn.delivery_status === 'interrupted' ? ' · interrupted' : ''}</span></div>
        <p>{turn.text || 'This turn could not be transcribed.'}</p>
      </li>
    })}</ol> : <p>No transcript turns are available for this interview.</p>}
  </details>
}
