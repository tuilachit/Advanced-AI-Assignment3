import type { TranscriptTurn } from './types'

export class TranscriptView {
  private rows = new Map<string, { row: HTMLElement; label: HTMLElement; body: Text; version: number }>()

  constructor(private container: HTMLElement) {}

  update(turn: TranscriptTurn): void {
    let record = this.rows.get(turn.turn_id)
    if (record && turn.transcript_version <= record.version) return
    if (!record) {
      const row = document.createElement('div')
      row.className = 'transcript-turn'
      const label = document.createElement('small')
      const body = document.createTextNode('')
      row.append(label, body)
      record = { row, label, body, version: 0 }
      this.rows.set(turn.turn_id, record)
      this.container.append(row)
    }
    record.version = turn.transcript_version
    record.row.hidden = !turn.text.trim() && turn.transcript_status !== 'failed'
    record.row.dataset.status = turn.transcript_status
    const status = turn.transcript_status === 'final' ? 'Final transcript'
      : turn.transcript_status === 'failed' ? 'Transcription unavailable' : 'Live caption — may change'
    record.label.textContent = `${turn.speaker === 'candidate' ? 'You' : 'Interviewer'} · ${status}${turn.delivery_status === 'interrupted' ? ' · interrupted' : ''}`
    // Preserve the Text node and avoid any DOM writes for timing-only updates.
    const value = turn.text || 'This turn could not be transcribed.'
    if (record.body.data !== value) record.body.data = value
  }

  clear(): void {
    this.rows.clear()
    this.container.replaceChildren()
  }
}
