import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Supplier } from '../types'
import { Empty, Loading } from '../components/ui'
import SupplierForm, { BLANK_SUPPLIER } from '../components/SupplierForm'

const NO_CATEGORY = '—'
const NO_COUNTRY = '—'

/** Tally one field across the list, most frequent first, blanks last. */
function tally(rows: Supplier[], pick: (s: Supplier) => string, blank: string) {
  const counts = new Map<string, number>()
  for (const s of rows) {
    const key = pick(s) || blank
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) =>
    a[0] === blank ? 1 : b[0] === blank ? -1 : b[1] - a[1],
  )
}

export default function Suppliers() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Supplier | Omit<Supplier, 'id'> | null>(null)
  const [category, setCategory] = useState('')
  const [country, setCountry] = useState('')
  const [q, setQ] = useState('')

  const { data, reload } = useLiveData<Supplier[]>(
    () => api.get('/api/suppliers?include_inactive=true'),
    [],
    (e) => e.startsWith('supplier'),
  )

  // Category tabs count the whole list, so their labels stay stable while filtering.
  const categories = useMemo(
    () => tally(data ?? [], (s) => s.category, NO_CATEGORY),
    [data],
  )
  // Country options follow the chosen category, so the two filters never disagree.
  const countries = useMemo(() => {
    const scope = category
      ? (data ?? []).filter((s) => (s.category || NO_CATEGORY) === category)
      : (data ?? [])
    return tally(scope, (s) => s.country, NO_COUNTRY)
  }, [data, category])

  const shown = useMemo(() => {
    let rows = data ?? []
    if (category) rows = rows.filter((s) => (s.category || NO_CATEGORY) === category)
    if (country) rows = rows.filter((s) => (s.country || NO_COUNTRY) === country)
    const needle = q.trim().toLowerCase()
    if (needle) rows = rows.filter((s) => s.name.toLowerCase().includes(needle))
    return rows
  }, [data, category, country, q])

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
          <button
            className={`tab ${category === '' ? 'active' : ''}`}
            onClick={() => {
              setCategory('')
              setCountry('')
            }}
          >
            Все · {data.length}
          </button>
          {categories.map(([name, count]) => (
            <button
              key={name}
              className={`tab ${category === name ? 'active' : ''}`}
              onClick={() => {
                setCategory(name)
                setCountry('') // country options are scoped to the category
              }}
            >
              {name === NO_CATEGORY ? 'Без категории' : name} · {count}
            </button>
          ))}
        </div>
      </div>

      <div className="filters">
        <input
          className="input grow"
          placeholder="Поиск по названию"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="select" value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="">Все страны</option>
          {countries.map(([name, count]) => (
            <option key={name} value={name}>
              {name === NO_COUNTRY ? 'Без страны' : name} · {count}
            </option>
          ))}
        </select>
        <span className="small faint nowrap">
          {shown.length} из {data.length}
        </span>
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
                : 'Под выбранный фильтр поставщики не подходят.'
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
          countries={tally(data, (s) => s.country, NO_COUNTRY)
            .filter(([n]) => n !== NO_COUNTRY)
            .map(([n]) => n)}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </>
  )
}
