const TOKEN_KEY = 'ved_token'

/** Vite's base path without the trailing slash: "" at root, "/ved" behind Caddy. */
const BASE = (((import.meta as any).env?.BASE_URL as string) || '/').replace(/\/$/, '')

/** Absolute URL for an API path — use this for any raw fetch() outside `api`. */
export function apiUrl(path: string): string {
  return BASE + path
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(apiUrl(path), { ...init, headers })

  // A 401 while signing in means bad credentials, not an expired session —
  // only treat it as expiry when we actually sent a token.
  const isLogin = path.startsWith('/api/auth/login')
  if (res.status === 401 && !isLogin) {
    setToken(null)
    onUnauthorized?.()
    throw new ApiError(401, 'Сессия истекла — войдите заново')
  }
  if (!res.ok) {
    let detail = `Ошибка ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: any) => d.msg).join('; ')
    } catch {
      /* keep default */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  del: <T = void,>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T,>(path: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<T>(path, { method: 'POST', body: fd })
  },
}

export function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${BASE}/ws?token=${encodeURIComponent(getToken() ?? '')}`
}
