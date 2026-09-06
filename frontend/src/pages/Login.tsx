import { useState, type FormEvent } from 'react'
import { useAuth } from '../store'
import { ErrorBox, Field } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (err: any) {
      setError(err?.message ?? 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card card" onSubmit={submit}>
        <div className="brand" style={{ padding: '0 0 18px' }}>
          <div className="brand-mark">ВЭД</div>
          <div className="brand-text">
            <b>Оперативный контроль ВЭД</b>
            <span>Real-time pipeline</span>
          </div>
        </div>

        <h2>Вход в систему</h2>
        <p className="sub">18 блоков процесса в реальном времени</p>

        {error && <ErrorBox message={error} />}

        <div style={{ display: 'grid', gap: 13 }}>
          <Field label="Логин">
            {/* type="text", not "email": logins may be plain usernames. */}
            <input
              className="input"
              type="text"
              value={email}
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="имя пользователя или email"
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </Field>
          <Field label="Пароль">
            <input
              className="input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: 'center' }}>
            {busy ? 'Вход…' : 'Войти'}
          </button>
        </div>

        <div className="hint">
          Логин не зависит от регистра. Новые учётные записи заводит администратор.
        </div>
      </form>
    </div>
  )
}
