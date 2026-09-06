import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { User } from '../types'
import { Empty, Field, Loading, Modal } from '../components/ui'
import { ROLE_LABELS } from '../util'

interface Role {
  key: string
  name: string
}

export default function Users() {
  const { user: me } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [roles, setRoles] = useState<Role[]>([])

  const { data, reload } = useLiveData<User[]>(
    () => api.get('/api/auth/users'),
    [],
    (e) => e.startsWith('user'),
  )

  useEffect(() => {
    api.get<Role[]>('/api/auth/roles').then(setRoles).catch(() => undefined)
  }, [])

  const isAdmin = me?.role === 'admin'

  if (!data) return <Loading />

  return (
    <>
      <p className="muted" style={{ marginTop: 0, maxWidth: 760 }}>
        Учётные записи и права доступа. Пользователей нельзя удалить — на них
        ссылаются сделки, отметки чек-листа и история. Вместо удаления переведите
        в архив: вход блокируется, а все прошлые записи остаются на месте.
      </p>

      <div className="filters">
        <div style={{ flex: 1 }} />
        {isAdmin && (
          <button className="btn primary" onClick={() => setCreating(true)}>
            + Пользователь
          </button>
        )}
      </div>

      {data.length === 0 ? (
        <div className="card">
          <Empty text="Пользователей нет." />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data" style={{ minWidth: 760 }}>
            <thead>
              <tr>
                <th>Логин</th>
                <th>Имя</th>
                <th>Роль</th>
                <th>Права</th>
                <th>Статус</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {data.map((u) => (
                <tr
                  key={u.id}
                  onClick={() => isAdmin && setEditing(u)}
                  style={{ cursor: isAdmin ? 'pointer' : 'default', opacity: u.is_active ? 1 : 0.55 }}
                >
                  <td className="mono nowrap">
                    {u.email}
                    {u.id === me?.id && (
                      <span className="badge blue" style={{ marginLeft: 7 }}>
                        это вы
                      </span>
                    )}
                  </td>
                  <td style={{ fontWeight: 550 }}>{u.full_name}</td>
                  <td className="nowrap">
                    <span className={`badge ${u.role === 'admin' ? 'amber' : ''}`}>
                      {ROLE_LABELS[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="small faint nowrap">
                    {u.role === 'viewer' ? 'только просмотр' : 'редактирование'}
                    {u.role === 'admin' && ' · всё'}
                    {u.role === 'director' && ' · нормативы'}
                  </td>
                  <td>
                    <span className={`badge ${u.is_active ? 'green' : ''}`}>
                      {u.is_active ? 'Активен' : 'Архив'}
                    </span>
                  </td>
                  {isAdmin && <td className="faint">›</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!isAdmin && (
        <div className="small faint mt">
          Изменять учётные записи может только администратор.
        </div>
      )}

      {creating && (
        <UserForm
          roles={roles}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false)
            reload()
          }}
        />
      )}
      {editing && (
        <UserForm
          roles={roles}
          existing={editing}
          isSelf={editing.id === me?.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
    </>
  )
}

function UserForm({
  roles,
  existing,
  isSelf,
  onClose,
  onSaved,
}: {
  roles: Role[]
  existing?: User
  isSelf?: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const { notify } = useToast()
  const [login, setLogin] = useState(existing?.email ?? '')
  const [fullName, setFullName] = useState(existing?.full_name ?? '')
  const [role, setRole] = useState(existing?.role ?? 'ved')
  const [isActive, setIsActive] = useState(existing?.is_active ?? true)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!login.trim()) return notify('Укажите логин', 'err')
    if (!fullName.trim()) return notify('Укажите имя', 'err')
    if (!existing && password.length < 4) return notify('Пароль — минимум 4 символа', 'err')
    if (existing && password && password.length < 4)
      return notify('Пароль — минимум 4 символа', 'err')

    setBusy(true)
    try {
      if (existing) {
        const body: Record<string, unknown> = {
          email: login.trim(),
          full_name: fullName.trim(),
          role,
          is_active: isActive,
        }
        if (password) body.password = password
        await api.patch(`/api/auth/users/${existing.id}`, body)
        notify('Сохранено')
      } else {
        await api.post('/api/auth/users', {
          email: login.trim(),
          full_name: fullName.trim(),
          role,
          password,
        })
        notify(`Пользователь ${login.trim()} создан`)
      }
      onSaved()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось сохранить', 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={existing ? `Пользователь: ${existing.email}` : 'Новый пользователь'}
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? 'Сохранение…' : existing ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Логин">
          <input
            className="input mono"
            value={login}
            autoFocus={!existing}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            placeholder="имя пользователя или email"
            onChange={(e) => setLogin(e.target.value)}
          />
        </Field>
        <Field label="Имя и фамилия">
          <input
            className="input"
            value={fullName}
            placeholder="Азиз Каримов"
            onChange={(e) => setFullName(e.target.value)}
          />
        </Field>
        <Field label="Роль">
          <select
            className="select"
            value={role}
            disabled={isSelf}
            onChange={(e) => setRole(e.target.value)}
          >
            {(roles.length ? roles : Object.entries(ROLE_LABELS).map(([key, name]) => ({ key, name }))).map(
              (r) => (
                <option key={r.key} value={r.key}>
                  {r.name}
                </option>
              ),
            )}
          </select>
        </Field>

        <Field label={existing ? 'Новый пароль' : 'Пароль'}>
          <input
            className="input"
            type="password"
            value={password}
            autoComplete="new-password"
            placeholder={existing ? 'оставьте пустым, чтобы не менять' : 'минимум 4 символа'}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>

        {existing && (
          <label
            className="row"
            style={{ gap: 8, cursor: isSelf ? 'not-allowed' : 'pointer' }}
          >
            <input
              type="checkbox"
              checked={isActive}
              disabled={isSelf}
              style={{ width: 16, height: 16, accentColor: 'var(--green)' }}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            <span className="small">Активен (может входить в систему)</span>
          </label>
        )}

        {isSelf && (
          <div className="hint">
            Это ваша учётная запись: роль и статус изменить нельзя, чтобы не
            потерять доступ к системе. Логин, имя и пароль менять можно.
          </div>
        )}
      </div>
    </Modal>
  )
}
