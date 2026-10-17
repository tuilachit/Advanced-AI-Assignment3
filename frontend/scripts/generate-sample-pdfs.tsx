import { spawnSync } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { renderToFile } from '@react-pdf/renderer'

import { CVPdfDocument } from '../src/components/CVPdfDocument'
import { sampleCVs } from '../src/samples/sampleCVs'

const outputDirectory = path.resolve(process.cwd(), '..', 'output', 'pdf')
await mkdir(outputDirectory, { recursive: true })

const sampleIndex = process.argv[2]

if (sampleIndex === undefined) {
  for (const index of sampleCVs.keys()) {
    const result = spawnSync(process.execPath, [fileURLToPath(import.meta.url), String(index)], {
      stdio: 'inherit',
    })
    if (result.status !== 0) process.exit(result.status ?? 1)
  }
} else {
  const sample = sampleCVs[Number(sampleIndex)]
  if (!sample) throw new Error(`Unknown sample index: ${sampleIndex}`)
  const outputPath = path.join(outputDirectory, sample.filename)
  await renderToFile(
    <CVPdfDocument
      cv={sample.cv}
      facts={sample.facts}
      targetJobTitle={sample.targetJobTitle}
    />,
    outputPath,
  )
  console.log(`Created ${outputPath}`)
}
