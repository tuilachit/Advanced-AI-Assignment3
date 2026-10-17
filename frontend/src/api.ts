import type {
  ApiErrorBody,
  CVDocument,
  CVGenerationResponse,
  FactInput,
  MessageResponse,
  ResumeEntryEdit,
  Session,
  TraceResponse,
} from './types'

const API_ROOT = import.meta.env.VITE_API_ROOT ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  code: string
  details: Record<string, unknown>

  constructor(body: ApiErrorBody) {
    super(body.error.message)
    this.name = 'ApiError'
    this.code = body.error.code
    this.details = body.error.details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = (await response.json()) as T | ApiErrorBody
  if (!response.ok) {
    throw new ApiError(body as ApiErrorBody)
  }
  return body as T
}

export const api = {
  createSession: () => request<Session>('/sessions', { method: 'POST' }),
  getSession: (sessionId: string) => request<Session>(`/sessions/${sessionId}`),
  getTrace: (sessionId: string) =>
    request<TraceResponse>(`/sessions/${sessionId}/trace`),
  sendMessage: (sessionId: string, message: string) =>
    request<MessageResponse>(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  confirmProfile: (sessionId: string) =>
    request<Session>(`/sessions/${sessionId}/profile/confirm`, { method: 'POST' }),
  updateProfile: (sessionId: string, facts: FactInput[]) =>
    request<Session>(`/sessions/${sessionId}/profile`, {
      method: 'PUT',
      body: JSON.stringify({ facts }),
    }),
  proposeResumeEntries: (sessionId: string) =>
    request<Session>(`/sessions/${sessionId}/resume-entries/propose`, { method: 'POST' }),
  updateResumeEntry: (sessionId: string, entryId: string, edit: ResumeEntryEdit) =>
    request<Session>(`/sessions/${sessionId}/resume-entries/${entryId}`, {
      method: 'PUT',
      body: JSON.stringify(edit),
    }),
  approveResumeEntry: (sessionId: string, entryId: string) =>
    request<Session>(`/sessions/${sessionId}/resume-entries/${entryId}/approve`, { method: 'POST' }),
  deleteResumeEntry: (sessionId: string, entryId: string) =>
    request<Session>(`/sessions/${sessionId}/resume-entries/${entryId}`, { method: 'DELETE' }),
  retrieveJobs: (sessionId: string) =>
    request<Session>(`/sessions/${sessionId}/jobs/retrieve`, { method: 'POST' }),
  selectJob: (sessionId: string, documentId: string) =>
    request<Session>(`/sessions/${sessionId}/jobs/${documentId}/select`, {
      method: 'POST',
    }),
  generateCV: (sessionId: string) =>
    request<CVGenerationResponse>(`/sessions/${sessionId}/cvs`, { method: 'POST' }),
  saveCV: (sessionId: string, cv: CVDocument) =>
    request<Session>(`/sessions/${sessionId}/cvs/${cv.cv_id}`, {
      method: 'PUT',
      body: JSON.stringify(cv),
    }),
  validateCV: (sessionId: string, cvId: string) =>
    request<Session>(`/sessions/${sessionId}/cvs/${cvId}/validate`, { method: 'POST' }),
  recordExport: (sessionId: string, cvId: string) =>
    request<Session>(`/sessions/${sessionId}/cvs/${cvId}/export`, { method: 'POST' }),
}
