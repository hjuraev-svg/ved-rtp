import { useEffect, useState } from 'react'
import { useAuth, useHashRoute, useLive } from './store'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Deals from './pages/Deals'
import DealDetail from './pages/DealDetail'
import Suppliers from './pages/Suppliers'
import Blocks from './pages/Blocks'
import Analytics from './pages/Analytics'
import Users from './pages/Users'
import { ROLE_LABELS } from './util'

const NAV: { path: string; label: string; icon: string; adminOnly?: boolean }[] = [
  { path: '', label: 'Дашборд', icon: '▦' },
  { path: 'deals', label: 'Сделки', icon: '☰' },
  { path: 'analytics', label: 'Аналитика', icon: '◔' },
  { path: 'suppliers', label: 'Поставщики', icon: '⚑' },
  { path: 'blocks', label: 'Справочник блоков', icon: '❑' },
  { path: 'users', label: 'Пользователи', icon: '☺', adminOnly: true },
]

const TITLES: Record<string, string> = {
  '': 'ВЭД / Внешнеэкономическая деятельность',
  deals: 'Сделки',
  analytics: 'Аналитика процесса',
  suppliers: 'Поставщики',
  blocks: 'Справочник блоков дашборда',
  users: 'Пользователи и доступ',
}

export default function App() {
  const { user, ready, logout } = useAuth()
  const { connected } = useLive()
  const [route, navigate, query] = useHashRoute()
  const [theme, setTheme] = useState(() => localStorage.getItem('ved_theme') ?? 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ved_theme', theme)
  }, [theme])

  if (!ready) return <div className="empty" style={{ paddingTop: 120 }}>Загрузка…</div>
  if (!user) return <Login />

  const section = route[0] ?? ''
  const title = section === 'deal' ? 'Карточка сделки' : (TITLES[section] ?? 'ВЭД')

  let page
  if (section === '') page = <Dashboard navigate={navigate} />
  else if (section === 'deals')
    page = (
      <Deals
        navigate={navigate}
        initialStage={query.stage ? Number(query.stage) : null}
        initialPipeline={query.pipeline ?? null}
      />
    )
  else if (section === 'deal') page = <DealDetail dealId={Number(route[1])} navigate={navigate} />
  else if (section === 'analytics') page = <Analytics />
  else if (section === 'suppliers') page = <Suppliers />
  else if (section === 'blocks') page = <Blocks />
  else if (section === 'users') page = <Users />
  else page = <div className="empty">Страница не найдена</div>

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ВЭД</div>
          <div className="brand-text">
            <b>Оперативный контроль</b>
            <span>Real-time pipeline</span>
          </div>
        </div>

        {NAV.filter((item) => !item.adminOnly || user.role === 'admin').map((item) => (
          <div
            key={item.path}
            className={`nav-item ${section === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span style={{ opacity: 0.7, width: 15, textAlign: 'center' }}>{item.icon}</span>
            {item.label}
          </div>
        ))}

        <div className="nav-spacer" />

        <div className="nav-item" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          <span style={{ opacity: 0.7, width: 15, textAlign: 'center' }}>
            {theme === 'dark' ? '☾' : '☀'}
          </span>
          {theme === 'dark' ? 'Тёмная тема' : 'Светлая тема'}
        </div>
        <div className="nav-item" onClick={logout}>
          <span style={{ opacity: 0.7, width: 15, textAlign: 'center' }}>⏻</span>
          Выйти
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <div className="spacer" />
          <span className={`live ${connected ? '' : 'off'}`}>
            <i className="dot" />
            {connected ? 'Онлайн' : 'Переподключение…'}
          </span>
          <span className="badge">
            {user.full_name} · {ROLE_LABELS[user.role] ?? user.role}
          </span>
        </header>
        <div className="content">{page}</div>
      </div>
    </div>
  )
}
