import { Document, Font, Page, StyleSheet, Text, View } from '@react-pdf/renderer'

import type { CVClaim, CVDocument, Fact } from '../types'

import { CONTACT_FIELD_ALIASES, isContactField } from '../contactFields'

Font.registerHyphenationCallback((word) => [word])

const CONTACT_FIELDS = ['email', 'phone', 'github', 'linkedin', 'portfolio', 'website']
const SECTION_ORDER: Record<string, number> = {
  summary: 0,
  profile: 0,
  education: 1,
  experience: 2,
  projects: 3,
  'selected projects': 3,
  'selected ai and software work': 3,
  skills: 4,
  'technical skills': 4,
  achievements: 5,
  interests: 6,
}

export const CV_PDF_LAYOUT = {
  nameBottomMargin: 10,
  headlineLineHeight: 1.2,
  footerTopMargin: 18,
} as const

const styles = StyleSheet.create({
  page: {
    paddingTop: 44,
    paddingRight: 48,
    paddingBottom: 48,
    paddingLeft: 48,
    color: '#000000',
    fontFamily: 'Times-Roman',
    fontSize: 10,
    lineHeight: 1.35,
  },
  header: { alignItems: 'center', marginBottom: 13 },
  name: {
    marginBottom: CV_PDF_LAYOUT.nameBottomMargin,
    color: '#000000',
    fontFamily: 'Times-Bold',
    fontSize: 24,
    lineHeight: 1.05,
  },
  contact: { marginBottom: 6, color: '#000000', fontSize: 9, textAlign: 'center' },
  headline: {
    color: '#000000',
    fontSize: 11,
    lineHeight: CV_PDF_LAYOUT.headlineLineHeight,
    textAlign: 'center',
  },
  targetJob: {
    marginTop: 5,
    color: '#000000',
    fontFamily: 'Times-Italic',
    fontSize: 9,
    textAlign: 'center',
  },
  rule: { marginBottom: 15, borderBottomWidth: 1, borderBottomColor: '#000000' },
  section: { marginBottom: 14 },
  heading: {
    marginBottom: 7,
    paddingBottom: 4,
    borderBottomWidth: 0.7,
    borderBottomColor: '#000000',
    color: '#000000',
    fontFamily: 'Times-Bold',
    fontSize: 10,
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  claimRow: { display: 'flex', flexDirection: 'row', marginBottom: 5 },
  bullet: { width: 12, color: '#000000', fontFamily: 'Times-Bold' },
  claim: { flex: 1, color: '#000000' },
  footer: {
    marginTop: CV_PDF_LAYOUT.footerTopMargin,
    color: '#000000',
    fontSize: 8,
    textAlign: 'center',
  },
})

export interface CvPdfSection {
  heading: string
  claims: CVClaim[]
}

export interface CvPdfContent {
  name: string
  contactLine: string | null
  headline: string
  targetJobTitle: string | null
  sections: CvPdfSection[]
  footer: string
  visibleText: string
}

export function buildCvPdfContent(
  cv: CVDocument,
  facts: Fact[],
  targetJobTitle?: string,
): CvPdfContent {
  const confirmedFacts = facts.filter((fact) => fact.status === 'confirmed')
  const factsById = new Map(confirmedFacts.map((fact) => [fact.fact_id, fact]))
  const name = confirmedFacts.find((fact) => fact.field === 'name')?.value ?? 'Candidate'
  const readableTargetJobTitle = targetJobTitle?.trim() || null
  const contactLine = CONTACT_FIELDS
    .map((field) => confirmedFacts.find((fact) => CONTACT_FIELD_ALIASES[field].includes(fact.field))?.value)
    .filter((value): value is string => Boolean(value))
    .join(' · ') || null
  const contactClaims = new Set(
    cv.claims
      .filter((claim) => isContactClaim(claim, factsById))
      .map((claim) => claim.claim_id),
  )
  const summaryClaims = cv.claims.filter((claim) => !contactClaims.has(claim.claim_id))
  const sections: CvPdfSection[] = [
    ...(summaryClaims.length ? [{ heading: 'Summary', claims: summaryClaims }] : []),
    ...cv.sections
      .filter((section) => section.claims.length > 0)
      .map((section, index) => ({ section, index }))
      .sort((left, right) => {
        const leftRank = SECTION_ORDER[left.section.heading.toLowerCase()] ?? 99
        const rightRank = SECTION_ORDER[right.section.heading.toLowerCase()] ?? 99
        return leftRank - rightRank || left.index - right.index
      })
      .map(({ section }) => ({ heading: section.heading, claims: section.claims })),
  ]
  const footer = 'Prepared from confirmed profile information.'
  const visibleText = [
    name,
    contactLine,
    cv.headline,
    readableTargetJobTitle ? `Application focus: ${readableTargetJobTitle}` : null,
    ...sections.flatMap((section) => [section.heading, ...section.claims.map((claim) => claim.text)]),
    footer,
  ].filter((value): value is string => Boolean(value)).join('\n')

  return {
    name,
    contactLine,
    headline: cv.headline,
    targetJobTitle: readableTargetJobTitle,
    sections,
    footer,
    visibleText,
  }
}

interface CVPdfDocumentProps {
  cv: CVDocument
  facts: Fact[]
  targetJobTitle?: string
}

export function CVPdfDocument({ cv, facts, targetJobTitle }: CVPdfDocumentProps) {
  const content = buildCvPdfContent(cv, facts, targetJobTitle)

  return (
    <Document title={`${content.name} CV`} author={content.name} subject="Evidence-backed CV">
      <Page size="A4" style={styles.page}>
        <View style={styles.header}>
          <Text style={styles.name}>{content.name}</Text>
          {content.contactLine ? <Text style={styles.contact}>{content.contactLine}</Text> : null}
          <Text style={styles.headline}>{content.headline}</Text>
          {content.targetJobTitle ? (
            <Text style={styles.targetJob}>Application focus: {content.targetJobTitle}</Text>
          ) : null}
        </View>
        <View style={styles.rule} />

        {content.sections.map((section) => (
          <CVSection heading={section.heading} claims={section.claims} key={section.heading} />
        ))}

        <Text style={styles.footer}>{content.footer}</Text>
      </Page>
    </Document>
  )
}

function isContactClaim(claim: CVClaim, factsById: Map<string, Fact>) {
  const facts = claim.fact_ids.map((factId) => factsById.get(factId))
  return facts.length > 0 && facts.every((fact) => fact && isContactField(fact.field))
}

function CVSection({ heading, claims }: { heading: string; claims: CVClaim[] }) {
  return (
    <View style={styles.section}>
      <Text style={styles.heading}>{heading}</Text>
      {claims.map((claim) => (
        <View style={styles.claimRow} key={claim.claim_id} wrap={false}>
          <Text style={styles.bullet}>-</Text>
          <Text style={styles.claim}>{claim.text}</Text>
        </View>
      ))}
    </View>
  )
}
