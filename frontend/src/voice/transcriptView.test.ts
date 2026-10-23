import { expect, it } from 'vitest'

import { TranscriptView } from './transcriptView'
import type { TranscriptTurn } from './types'

function turn(id: string, version: number, text: string, status: TranscriptTurn['transcript_status'] = 'partial'): TranscriptTurn {
  return { turn_id: id, question_id: 'q1', speaker: 'candidate', input_mode: 'live_voice',
    transcript_version: version, transcript_status: status, text, timing: null, delivery_status: 'not_applicable' }
}

it('updates one stable row without replacing prior turns', () => {
  const container = document.createElement('div')
  const view = new TranscriptView(container)
  view.update(turn('one', 1, 'Python.', 'final'))
  const first = container.firstElementChild
  view.update(turn('two', 1, 'I used'))
  const second = container.lastElementChild
  view.update(turn('two', 2, 'I used SQL.'))
  expect(container.children).toHaveLength(2)
  expect(container.firstElementChild).toBe(first)
  expect(container.lastElementChild).toBe(second)
  expect(second?.textContent).toContain('I used SQL.')
})

it('hides empty pending turns, retains their order, and ignores stale revisions', () => {
  const container = document.createElement('div')
  const view = new TranscriptView(container)
  view.update(turn('one', 1, '', 'pending'))
  expect((container.firstElementChild as HTMLElement).hidden).toBe(true)
  view.update(turn('two', 1, 'Second.', 'final'))
  view.update(turn('one', 3, 'First.', 'final'))
  view.update(turn('one', 2, 'Stale partial'))
  expect((container.firstElementChild as HTMLElement).hidden).toBe(false)
  expect(container.firstElementChild?.textContent).toContain('First.')
  expect(container.textContent).not.toContain('Stale partial')
  expect(container.lastElementChild?.textContent).toContain('Second.')
})

it('renders speech as plain text and clears only when a new interview starts', () => {
  const container = document.createElement('div')
  const view = new TranscriptView(container)
  view.update(turn('one', 1, '<img src=x onerror=alert(1)>', 'final'))
  expect(container.querySelector('img')).toBeNull()
  expect(container.textContent).toContain('<img')
  view.clear()
  expect(container.children).toHaveLength(0)
})
