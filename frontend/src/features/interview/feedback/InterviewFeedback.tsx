import { useState } from 'react'
import type { Interview } from '../../../types'
import { FeedbackStage } from './FeedbackStage'
import { createSampleFeedback } from './sampleFeedback'

// No speculative feedback endpoint: the real report source will be bound here
// once Sunny's routes and generated API types are available.
export function InterviewFeedback({ interview, onBack, onSetup }: {
  interview: Interview; onBack: () => void; onSetup: () => void
}) {
  const [sample, setSample] = useState<ReturnType<typeof createSampleFeedback> | null>(null)
  if (sample) return <FeedbackStage key="sample" interview={sample.interview} source={sample.source}
    backLabel="Back to your interview summary" onBack={() => setSample(null)} onSetup={onSetup} />
  return <FeedbackStage key={interview.interview_id} interview={interview} source={null} onBack={onBack} onSetup={onSetup}
    onViewSample={() => setSample(createSampleFeedback())} />
}
