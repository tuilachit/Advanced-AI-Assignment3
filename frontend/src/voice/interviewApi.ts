import { ApiError } from '../api'
import type { ApiErrorBody } from '../types'
import type { InterviewApi } from './types'

export function interviewApi(session_id: string, root = import.meta.env.VITE_API_ROOT ?? 'http://localhost:8000/api'): InterviewApi {
  const base = `${root}/sessions/${encodeURIComponent(session_id)}/interviews`
  async function request<T>(id: string, action = '', body?: unknown): Promise<T> {
    const response = await fetch(`${base}/${encodeURIComponent(id)}${action ? `/${action}` : ''}`, {
      method: action ? 'POST' : 'GET', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    const data = await response.json()
    if (!response.ok) throw new ApiError(data as ApiErrorBody)
    return data as T
  }
  return {
    get: (id) => request(id),
    start: (id, body) => request(id, 'start', body),
    token: (id) => request(id, 'realtime-token', {}),
    turn: (id, body) => request(id, 'turns', body),
    next: (id, body) => request(id, 'next-step', body),
    skip: (id, body) => request(id, 'skip', body),
    end: (id, body) => request(id, 'end', body),
  }
}
