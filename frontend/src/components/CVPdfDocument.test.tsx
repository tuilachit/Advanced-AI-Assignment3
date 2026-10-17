// @vitest-environment node

import { renderToBuffer } from '@react-pdf/renderer'
import { describe, expect, it } from 'vitest'

import { buildCvPdfContent, CV_PDF_LAYOUT, CVPdfDocument } from './CVPdfDocument'
import type { CVDocument, Fact } from '../types'

const facts: Fact[] = [
  {
    fact_id: 'fact-name',
    field: 'name',
    value: 'Maya Chen',
    status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: 'student_profile_01' },
  },
  {
    fact_id: 'fact-email', field: 'email', value: 'maya.chen@example.com', status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: 'student_profile_01' },
  },
  {
    fact_id: 'fact-phone', field: 'phone', value: '0400 000 000', status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: 'student_profile_01' },
  },
  {
    fact_id: 'fact-study', field: 'education',
    value: 'Third-year Computing Science student at UTS', status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: 'student_profile_01' },
  },
  {
    fact_id: 'fact-project', field: 'project',
    value: 'Built a Python service layer for a course-planning API.', status: 'confirmed',
    source: { source_type: 'imported_test_profile', reference: 'student_profile_01' },
  },
]

const cv: CVDocument = {
  cv_id: 'cv-sample-01',
  target_job_id: 'graduate_ai_engineer',
  headline: 'Python API project experience',
  headline_fact_ids: ['fact-project'],
  claims: [
    {
      claim_id: 'claim-name', text: 'Maya Chen', fact_ids: ['fact-name'], verified: true,
    },
    {
      claim_id: 'claim-email', text: 'maya.chen@example.com', fact_ids: ['fact-email'], verified: true,
    },
    {
      claim_id: 'claim-01',
      text: 'Built a Python service layer for a course-planning API.',
      fact_ids: ['fact-project'],
      verified: true,
    },
  ],
  sections: [
    {
      heading: 'Technical skills',
      claims: [{
        claim_id: 'claim-skills', text: 'Python and SQL', fact_ids: ['fact-project'], verified: true,
      }],
    },
    {
      heading: 'Education',
      claims: [{
        claim_id: 'claim-education', text: 'Third-year Computing Science student at UTS',
        fact_ids: ['fact-study'], verified: true,
      }],
    },
  ],
}

describe('CVPdfDocument', () => {
  it('keeps the name and headline visually separated in the PDF header', () => {
    expect(CV_PDF_LAYOUT.nameBottomMargin).toBeGreaterThanOrEqual(8)
    expect(CV_PDF_LAYOUT.headlineLineHeight).toBeGreaterThanOrEqual(1.15)
    expect(CV_PDF_LAYOUT.footerTopMargin).toBeGreaterThanOrEqual(14)
  })

  it('builds a reader-facing Harvard-style content model without internal job IDs', () => {
    const content = buildCvPdfContent(cv, facts, 'Graduate AI Engineer')

    expect(content.name).toBe('Maya Chen')
    expect(content.contactLine).toBe('maya.chen@example.com · 0400 000 000')
    expect(content.targetJobTitle).toBe('Graduate AI Engineer')
    expect(content.sections.map((section) => section.heading)).toEqual([
      'Summary',
      'Education',
      'Technical skills',
    ])
    expect(content.visibleText).toContain('Application focus: Graduate AI Engineer')
    expect(content.visibleText).not.toContain('rag_agent_engineer')
    expect(content.visibleText).not.toContain('Target job evidence')
    expect(content.footer).toBe('Prepared from confirmed profile information.')
  })

  it('keeps two jobs visibly distinct for the same confirmed profile', () => {
    const first = buildCvPdfContent(cv, facts, 'Graduate AI Engineer')
    const second = buildCvPdfContent(cv, facts, 'AI Engineer - agentic workflows')

    expect(first.visibleText).not.toBe(second.visibleText)
    expect(first.visibleText).toContain('Application focus: Graduate AI Engineer')
    expect(second.visibleText).toContain('Application focus: AI Engineer - agentic workflows')
  })

  it('renders a valid PDF from a verified structured CV', async () => {
    const buffer = await renderToBuffer(<CVPdfDocument cv={cv} facts={facts} />)

    expect(buffer.subarray(0, 5).toString()).toBe('%PDF-')
    expect(buffer.byteLength).toBeGreaterThan(1_000)
  })
})
