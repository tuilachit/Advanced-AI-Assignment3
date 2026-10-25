import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Session } from '../types'
import { ProfileStage } from './ProfileStage'

const session: Session = {
  session_id: 'formatting-test', state: 'collecting_profile',
  profile: { facts: [], revision: 0 }, resume_entries: [], resume_entries_revision: 0,
  resume_entry_validation_issues: [], retrieval_results: [], selected_job_id: null,
  cv: null, validation_issues: [], validated_content_hash: null, trace: [],
}

describe('CV guide message formatting', () => {
  it('renders paragraphs, emphasis and nested lists instead of Markdown markers', () => {
    const { container } = render(<ProfileStage session={session} busy={false}
      onSendMessage={vi.fn()} onConfirm={vi.fn()} messages={[{ role: 'assistant', text:
        'Before I retrieve suitable jobs, please:\n\n1. Review and confirm your facts.\n2. Choose a primary title:\n   - **AI Engineer**\n   - **AI Product Engineer**\n\nYou can emphasise **retrieval/RAG**.',
      }]} />)
    expect(screen.getByText('AI Engineer').tagName).toBe('STRONG')
    expect(container.querySelectorAll('.assistant-message ol > li')).toHaveLength(2)
    expect(container.querySelectorAll('.assistant-message ol ul > li')).toHaveLength(2)
    expect(container.querySelectorAll('.assistant-message p')).toHaveLength(2)
    expect(container.querySelector('.assistant-message')).not.toHaveTextContent('**')
  })

  it('does not execute raw HTML, render external images or allow unsafe links', () => {
    const { container } = render(<ProfileStage session={session} busy={false}
      onSendMessage={vi.fn()} onConfirm={vi.fn()} messages={[{ role: 'assistant', text:
        '<script>alert("unsafe")</script>\n\n<img src="https://example.com/track" />\n\n![tracker](https://example.com/track)\n\n[unsafe](javascript:alert%281%29)\n\n[Portfolio](https://example.com)',
      }]} />)
    expect(container.querySelector('.assistant-message script')).toBeNull()
    expect(container.querySelector('.assistant-message img')).toBeNull()
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(screen.getByRole('link', { name: 'Portfolio' })).toHaveAttribute('href', 'https://example.com')
  })

  it('preserves the user’s original plain-text message', () => {
    const { container } = render(<ProfileStage session={session} busy={false}
      onSendMessage={vi.fn()} onConfirm={vi.fn()}
      messages={[{ role: 'user', text: '**My original wording**\n- My project' }]} />)
    expect(screen.getByText(/My original wording/)).toHaveTextContent('**My original wording**')
    expect(container.querySelector('.user-message strong')).toBeNull()
  })
})
