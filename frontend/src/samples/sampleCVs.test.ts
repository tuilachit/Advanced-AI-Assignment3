import { describe, expect, it } from 'vitest'

import { sampleCVs } from './sampleCVs'

describe('reviewed sample CV data', () => {
  it('contains three traceable CVs with only confirmed fact references', () => {
    expect(sampleCVs).toHaveLength(3)
    expect(sampleCVs[0].profileDocumentId).toBe(sampleCVs[1].profileDocumentId)
    expect(sampleCVs[0].cv.target_job_id).not.toBe(sampleCVs[1].cv.target_job_id)
    expect(sampleCVs[2].profileDocumentId).not.toBe(sampleCVs[0].profileDocumentId)

    for (const sample of sampleCVs) {
      const confirmedFactIds = new Set(
        sample.facts.filter((fact) => fact.status === 'confirmed').map((fact) => fact.fact_id),
      )
      const claims = [sample.cv.claims, ...sample.cv.sections.map((section) => section.claims)].flat()

      expect(sample.filename).toMatch(/^[a-z0-9-]+\.pdf$/)
      expect(sample.cv.headline_fact_ids.length).toBeGreaterThan(0)
      expect(sample.cv.headline_fact_ids.every((id) => confirmedFactIds.has(id))).toBe(true)
      expect(claims.length).toBeGreaterThan(2)
      expect(claims.every((claim) => claim.verified)).toBe(true)
      expect(claims.every((claim) => claim.fact_ids.length > 0)).toBe(true)
      expect(claims.every((claim) => claim.fact_ids.every((id) => confirmedFactIds.has(id)))).toBe(true)
    }
  })
})
