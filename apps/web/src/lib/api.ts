/**
 * Typed API client.
 *
 * One place owns the base URL, the auth header, the error envelope and the
 * 401 handling, so no component has to think about any of it.
 */
import { useAuthStore } from '@/store/auth'

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
export const API_BASE = RAW_BASE.replace(/\/$/, '')
export const API_PREFIX = `${API_BASE}/api/v1`

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  requestId: string | null

  constructor(status: number, code: string, message: string, details: unknown, requestId: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  raw?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, raw, headers, ...rest } = options
  const token = useAuthStore.getState().token

  const finalHeaders = new Headers(headers)
  if (token) finalHeaders.set('Authorization', `Bearer ${token}`)
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401) {
    // Token expired or revoked: drop it so the router sends the user to sign-in.
    useAuthStore.getState().clear()
  }

  if (!response.ok) {
    let code = 'http_error'
    let message = `Request failed with status ${response.status}`
    let details: unknown = null
    try {
      const payload = await response.json()
      if (payload?.error) {
        code = payload.error.code ?? code
        message = payload.error.message ?? message
        details = payload.error.details ?? null
      }
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(response.status, code, message, details, response.headers.get('X-Request-ID'))
  }

  if (response.status === 204) return undefined as T
  if (raw) return (await response.text()) as unknown as T
  return (await response.json()) as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
  text: (path: string) => request<string>(path, { raw: true }),
  upload: <T,>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
}

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}
