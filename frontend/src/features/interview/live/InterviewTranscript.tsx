import { useEffect, useRef, useState } from 'react'

import type { TranscriptTurn } from '../../../types'

export function InterviewTranscript({ turns }: { turns: TranscriptTurn[] }) {
  const panel = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const [following, setFollowing] = useState(true)
  const visibleTurns = turns.filter((turn) => turn.text.trim() || turn.transcript_status === 'failed')
  useEffect(() => {
    if (follow.current && panel.current) panel.current.scrollTop = panel.current.scrollHeight
  }, [turns])

  return <section className="live-transcript" aria-labelledby="transcript-title">
    <div className="live-transcript-heading"><div><h3 id="transcript-title">Live transcript</h3>
      <p>Live captions may change before they become final.</p></div>
      {!following ? <button className="interview-text-button" type="button" onClick={() => {
        follow.current = true
        setFollowing(true)
        if (panel.current) panel.current.scrollTop = panel.current.scrollHeight
      }}>Jump to latest</button> : null}
    </div>
    <div className="live-transcript-scroll" ref={panel} role="region" aria-label="Interview transcript" tabIndex={0}
      onScroll={() => {
        const node = panel.current
        if (!node) return
        follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40
        setFollowing(follow.current)
      }}>
      {visibleTurns.length ? <ol>{visibleTurns.map((turn) => <li key={turn.turn_id} data-status={turn.transcript_status}>
        <div className="transcript-turn-meta"><strong>{turn.speaker === 'candidate' ? 'You' : 'Interviewer'}</strong>
          <span>{turn.transcript_status === 'final' ? 'Final transcript' : turn.transcript_status === 'failed'
            ? 'Transcription unavailable' : 'Live caption · may change'}
            {turn.delivery_status === 'interrupted' ? ' · interrupted' : ''}</span></div>
        <p>{turn.text || 'This turn could not be transcribed.'}</p>
      </li>)}</ol> : <div className="transcript-empty"><p>Your conversation will appear here.</p>
        <span>Nothing is recorded until you start the interview.</span></div>}
    </div>
  </section>
}
