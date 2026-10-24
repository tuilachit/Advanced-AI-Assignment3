import type { SpeakingMeasure } from './feedbackView'

const labels: Record<SpeakingMeasure['key'], string> = { pace: 'Speaking pace', fillers: 'Transcript fillers', pauses: 'Pauses' }

export function SpeakingMetrics({ measures }: { measures: SpeakingMeasure[] }) {
  return <section className="feedback-speaking" aria-label="Speaking metrics for this answer">
    <h4>Speaking metrics for this answer</h4>
    <p className="feedback-help">These describe the available speech evidence. They are not scores.</p>
    <div className="feedback-metrics-grid">{measures.map((measure) => <section className="feedback-metric" aria-label={labels[measure.key]} key={measure.key}>
      <h5>{labels[measure.key]}</h5>
      {measure.measurement.kind === 'available' ? <p className="feedback-metric-value"><strong>{new Intl.NumberFormat('en-AU', { maximumFractionDigits: 2 }).format(measure.measurement.value)}</strong>
        <span>{measure.measurement.unit === 'words/min' ? 'words/min' : 'count'}</span></p>
        : <><p className="feedback-metric-unavailable">Not available</p><p>{measure.measurement.reason}</p></>}
      <details><summary>Method &amp; coverage</summary><p>{measure.method}</p>
        <p>{measure.turnIds.length} {measure.turnIds.length === 1 ? 'transcript turn used' : 'transcript turns used'}.</p></details>
    </section>)}</div>
  </section>
}
