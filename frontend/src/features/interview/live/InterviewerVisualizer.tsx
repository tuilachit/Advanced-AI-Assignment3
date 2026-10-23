import type { VisualizerProps, VisualizerState } from './voiceBridge'

export const visualizerCopy: Record<VisualizerState, [string, string]> = {
  ready: ['Ready when you are', 'Take a breath. Start when you’re comfortable.'],
  connecting: ['Connecting to your interviewer', 'Your browser may ask for microphone access.'],
  listening: ['Listening', 'Take your time and answer in your own words.'],
  speaking: ['Your interviewer is speaking', 'Listen to the question, then share your experience.'],
  'user-speaking': ['You have the floor', 'Your live caption will appear in the transcript.'],
  muted: ['Microphone muted', 'Unmute to continue. Your time limit keeps running.'],
  error: ['Connection needs attention', 'Check the message below before continuing.'],
  finalizing: ['Finishing your interview', 'Waiting for captured speech to finish transcribing.'],
  finished: ['Your practice is complete', 'You can review the transcript below.'],
}

// Presentation-only slot: replace with a React wrapper for Luke's VoiceOrbView,
// or an avatar. Neither this component nor its animation controls audio or flow.
export function InterviewerVisualizer({ state }: VisualizerProps) {
  return <div className="interviewer-visualizer" data-state={state} aria-hidden="true">
    <div className="interviewer-halo" /><div className="interviewer-orb"><span /><span /><span /></div>
  </div>
}
