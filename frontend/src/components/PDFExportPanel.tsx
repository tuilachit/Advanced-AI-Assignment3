import { pdf } from '@react-pdf/renderer'
import { useEffect, useRef, useState } from 'react'

import type { CVDocument, Fact } from '../types'
import { CVPdfDocument } from './CVPdfDocument'

interface PDFExportPanelProps {
  cv: CVDocument
  facts: Fact[]
  targetJobTitle?: string
  onExport: () => Promise<void>
  busy: boolean
}

export default function PDFExportPanel({ cv, facts, targetJobTitle, onExport, busy }: PDFExportPanelProps) {
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])
  const name = facts.find((fact) => fact.field === 'name')?.value ?? 'candidate'
  const filename = `${name.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}-cv.pdf`

  async function download() {
    setPreparing(true)
    setError(null)
    try {
      const blob = await pdf(<CVPdfDocument cv={cv} facts={facts} targetJobTitle={targetJobTitle} />).toBlob()
      if (!active.current) return
      await onExport()
      if (!active.current) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      if (active.current) setError(reason instanceof Error ? reason.message : 'PDF export failed. Please try again.')
    } finally {
      if (active.current) setPreparing(false)
    }
  }
  return (
    <div className="export-ready">
      <CheckIcon />
      <h4>Evidence gate passed</h4>
      <p>This exact CV is ready for local PDF rendering.</p>
      <button
        className="primary-button download-link"
        disabled={busy || preparing}
        onClick={() => { void download() }}
      >
        {preparing ? 'Preparing PDF…' : 'Download PDF'}
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
  )
}
