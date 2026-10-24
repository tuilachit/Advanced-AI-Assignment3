import { useState } from 'react'
import type { Interview } from '../../../types'
import { FeedbackStage } from './FeedbackStage'
import { createSampleFeedback } from './sampleFeedback'
import { feedbackService } from './feedbackService'
import type { FeedbackSource } from './feedbackView'

// The scripted live preview explicitly supplies null; it never calls the API.
export function InterviewFeedback({ interview, onBack, onSetup, source = feedbackService, visible = true }: {
  interview: Interview; onBack: () => void; onSetup: () => void; source?: FeedbackSource | null; visible?: boolean
}) {
  const [sample, setSample] = useState<ReturnType<typeof createSampleFeedback> | null>(null)
  if (sample) return <FeedbackStage key="sample" interview={sample.interview} source={sample.source}
    backLabel="Back to your interview summary" onBack={() => setSample(null)} onSetup={onSetup} visible={visible} />
  return <FeedbackStage key={interview.interview_id} interview={interview} source={source} onBack={onBack} onSetup={onSetup} visible={visible}
    onViewSample={() => setSample(createSampleFeedback())} />
}
