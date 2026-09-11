import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Supplier } from '../types'
import { Empty, Loading } from '../components/ui'
import SupplierForm, { BLANK_SUPPLIER } from '../components/SupplierForm'

const NO_CATEGORY = '—'

export default function Suppliers() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Supplier | Omit<Supplier, 'id'> | null>(null)
  const [category, setCategory] = useState('')

  const { data, reload } = useLiveData<Supplier[]>(
    () => api.get('/api/suppliers?include_inactive=true'),
    [],
    (e) => e.startsWith('supplier'),
  )

  // Counts come from the full list so the tab labels stay stable while filtering.
  const categories = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of data ?? []) {
      const key = s.category || NO_CATEGORY
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) =>
      a[0] === NO_CATEGORY ? 1 : b[0] === NO_CATEGORY ? -1 : b[1] - a[1],
    )
  }, [data])

  const shown = useMemo(() => {
    if (!data) return []
    if (!category) return data
    return data.filter((s) => (s.category || NO_CATEGORY) === category)
  }, [data, category])

  async function save(form: Supplier | Omit<Supplier, 'id'>) {
    if (!form.name.trim()) return notify('Укажите название', 'err')
    try {
      const body = { ...form, name: form.name.trim() }
      if ('id' in form) await api.patch(`/api/suppliers/${form.id}`, body)
      else await api.post('/api/suppliers', body)
      notify('Сохранено')
      setEditing(null)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  if (!data) return <Loading />

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="tabs">
          <button className={`tab ${category === '' ? 'active' : ''}`} onClick={() => setCategory('')}>
            Все · {data.length}
          </button>
          {categories.map(([name, count]) => (
            <button
              key={name}
              className={`tab ${category === name ? 'active' : ''}`}
              onClick={() => setCategory(name)}
            >
              {name === NO_CATEGORY ? 'Без категории' : name} · {count}
            </button>
          ))}
        </div>
      </div>

      <div className="filters">
        <div style={{ flex: 1 }} />
        {canEdit && (
          <button className="btn primary" onClick={() => setEditing({ ...BLANK_SUPPLIER })}>
            + Поставщик
          </button>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="card">
          <Empty
            text={
              data.length === 0
                ? 'Поставщики пока не заведены.'
                : 'В этой категории поставщиков нет.'
            }
          />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Название</th>
                <th>Категория</th>
                <th>Страна</th>
                <th>Контактное лицо</th>
                <th>Мессенджер / канал</th>
                <th>Email</th>
                <th>Телефон</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => (
                <tr key={s.id} onClick={() => canEdit && setEditing(s)}>
                  <td>
                    <b style={{ fontWeight: 550 }}>{s.name}</b>
                  </td>
                  <td>
                    {s.category ? <span className="badge">{s.category}</span> : '—'}
                  </td>
                  <td>{s.country || '—'}</td>
                  <td>{s.contact_person || '—'}</td>
                  <td className="small">{s.messenger || '—'}</td>
                  <td className="small faint">{s.email || '—'}</td>
                  <td className="small faint nowrap">{s.phone || '—'}</td>
                  <td>
                    <span className={`badge ${s.is_active ? 'green' : ''}`}>
                      {s.is_active ? 'Активен' : 'Архив'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <SupplierForm
          supplier={editing}
          categories={categories.filter(([n]) => n !== NO_CATEGORY).map(([n]) => n)}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </>
  )
}
