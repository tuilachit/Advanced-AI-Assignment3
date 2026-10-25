import type { VisualizerProps, VisualizerState } from './voiceBridge'
import './interviewerVisualizer.css'

export const visualizerCopy: Record<VisualizerState, [string, string]> = {
  ready: ['Ready when you are', 'Take a breath. Start when you’re comfortable.'],
  connecting: ['Connecting to your interviewer', 'Your browser may ask for microphone access.'],
  listening: ['Listening', 'Take your time and answer in your own words.'],
  speaking: ['Your interviewer is speaking', 'Listen to the question, then share your experience.'],
  'user-speaking': ['You have the floor', 'Your live caption will appear in the transcript.'],
  muted: ['Microphone muted', 'Unmute to continue. Your time limit keeps running.'],
  disconnected: ['Voice disconnected', 'Reconnect when you’re ready. Your saved transcript stays here.'],
  error: ['Connection needs attention', 'Check the message below before continuing.'],
  finalizing: ['Finishing your interview', 'Waiting for captured speech to finish transcribing.'],
  finished: ['Your practice is complete', 'You can review the transcript below.'],
}

// Decorative, state-driven motion only: the public voice events contain no audio
// levels. No analyser, microphone access, subscription or animation timer belongs
// here. The adjacent live status supplies accessible text; this slot can later
// host another visualizer or avatar without changing controller ownership.
export function InterviewerVisualizer({ state }: VisualizerProps) {
  return <div className="interviewer-visualizer" data-state={state} aria-hidden="true">
    <div className="interviewer-halo" />
    <div className="interviewer-orbit" />
    <div className="interviewer-ripples" />
    <div className="interviewer-orb">
      <span className="interviewer-orb-current interviewer-orb-current--blue" />
      <span className="interviewer-orb-current interviewer-orb-current--sage" />
      <span className="interviewer-orb-light" />
      <span className="interviewer-orb-symbol">
        {state === 'muted' ? <svg viewBox="0 0 24 24" focusable="false">
          <path d="M9 9v3a3 3 0 0 0 5.1 2.1M15 9V5a3 3 0 0 0-5.8-1M5 10v2a7 7 0 0 0 12 4.9M19 10v2M12 19v3M8 22h8M3 3l18 18" />
        </svg> : state === 'disconnected' ? <svg viewBox="0 0 24 24" focusable="false">
          <path d="m9 15 6-6M8 6l2-2a5 5 0 0 1 7 7l-2 2M16 18l-2 2a5 5 0 0 1-7-7l2-2M3 3l18 18" />
        </svg> : state === 'error' ? <svg viewBox="0 0 24 24" focusable="false">
          <path d="M12 5v9M12 19v.1" />
        </svg> : state === 'finished' ? <svg viewBox="0 0 24 24" focusable="false">
          <path d="m5 12 4 4L19 6" />
        </svg> : null}
      </span>
    </div>
  </div>
}
