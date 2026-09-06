import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api, getToken, setToken, setUnauthorizedHandler, wsUrl } from './api'
import type { User } from './types'

// ---------------------------------------------------------------- auth
interface AuthCtx {
  user: User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  canEdit: boolean
}

const AuthContext = createContext<AuthCtx>(null as never)
export const useAuth = () => useContext(AuthContext)

const EDIT_ROLES = ['admin', 'ved', 'director', 'logist', 'warehouse', 'accountant', 'broker']

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    if (!getToken()) {
      setReady(true)
      return
    }
    api
      .get<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/api/auth/login', {
      email,
      password,
    })
    setToken(res.access_token)
    setUser(res.user)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    location.hash = '#/'
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, ready, login, logout, canEdit: !!user && EDIT_ROLES.includes(user.role) }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// ---------------------------------------------------------------- realtime
type Listener = (event: string, payload: any) => void

interface LiveCtx {
  connected: boolean
  subscribe: (fn: Listener) => () => void
  lastEventAt: number
}

const LiveContext = createContext<LiveCtx>(null as never)
export const useLive = () => useContext(LiveContext)

export function LiveProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [connected, setConnected] = useState(false)
  const [lastEventAt, setLastEventAt] = useState(0)
  const listeners = useRef(new Set<Listener>())
  const socket = useRef<WebSocket | null>(null)
  const retry = useRef(0)
  const timer = useRef<number | undefined>(undefined)

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }, [])

  useEffect(() => {
    if (!user) {
      socket.current?.close()
      socket.current = null
      setConnected(false)
      return
    }

    let cancelled = false

    const connect = () => {
      if (cancelled) return
      const ws = new WebSocket(wsUrl())
      socket.current = ws

      ws.onopen = () => {
        retry.current = 0
        setConnected(true)
      }
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.event === 'ping' || msg.event === 'hello') return
          setLastEventAt(Date.now())
          listeners.current.forEach((fn) => fn(msg.event, msg.payload))
        } catch {
          /* ignore malformed frames */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (cancelled) return
        // exponential backoff, capped at 15s
        const delay = Math.min(1000 * 2 ** retry.current, 15000)
        retry.current += 1
        timer.current = window.setTimeout(connect, delay)
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      cancelled = true
      window.clearTimeout(timer.current)
      socket.current?.close()
      socket.current = null
    }
  }, [user])

  return (
    <LiveContext.Provider value={{ connected, subscribe, lastEventAt }}>
      {children}
    </LiveContext.Provider>
  )
}

/** Re-run `fn` whenever the server broadcasts a change (and once on mount). */
export function useLiveData<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
  filter?: (event: string) => boolean,
) {
  const { subscribe } = useLive()
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const reload = useCallback(async () => {
    try {
      const result = await fnRef.current()
      setData(result)
      setError(null)
    } catch (e: any) {
      setError(e?.message ?? 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    return subscribe((event) => {
      if (!filter || filter(event)) reload()
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribe, reload, ...deps])

  return { data, error, loading, reload }
}

// ---------------------------------------------------------------- toast
interface ToastCtx {
  notify: (message: string, kind?: 'ok' | 'err') => void
}
const ToastContext = createContext<ToastCtx>(null as never)
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; kind: string } | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const notify = useCallback((message: string, kind: 'ok' | 'err' = 'ok') => {
    setToast({ message, kind })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToast(null), 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      {toast && <div className={`toast ${toast.kind === 'err' ? 'err' : ''}`}>{toast.message}</div>}
    </ToastContext.Provider>
  )
}

// ---------------------------------------------------------------- hash router
/** `#/deal/12?tab=docs` -> parts ['deal','12'], query {tab:'docs'} */
export function useHashRoute(): [string[], (path: string) => void, Record<string, string>] {
  const [hash, setHash] = useState(() => location.hash.replace(/^#\/?/, ''))

  useEffect(() => {
    const onChange = () => setHash(location.hash.replace(/^#\/?/, ''))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((path: string) => {
    location.hash = `#/${path.replace(/^\//, '')}`
  }, [])

  const [path, search = ''] = hash.split('?')
  const query = Object.fromEntries(new URLSearchParams(search).entries())

  return [path.split('/').filter(Boolean), navigate, query]
}
