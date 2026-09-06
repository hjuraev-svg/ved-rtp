import { useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Supplier } from '../types'
import { Empty, Loading } from '../components/ui'
import SupplierForm, { BLANK_SUPPLIER } from '../components/SupplierForm'

export default function Suppliers() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Supplier | Omit<Supplier, 'id'> | null>(null)

  const { data, reload } = useLiveData<Supplier[]>(
    () => api.get('/api/suppliers?include_inactive=true'),
    [],
    (e) => e.startsWith('supplier'),
  )

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
      <div className="filters">
        <div style={{ flex: 1 }} />
        {canEdit && (
          <button className="btn primary" onClick={() => setEditing({ ...BLANK_SUPPLIER })}>
            + Поставщик
          </button>
        )}
      </div>

      {data.length === 0 ? (
        <div className="card">
          <Empty text="Поставщики пока не заведены." />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Название</th>
                <th>Страна</th>
                <th>Контактное лицо</th>
                <th>Мессенджер / канал</th>
                <th>Email</th>
                <th>Телефон</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id} onClick={() => canEdit && setEditing(s)}>
                  <td>
                    <b style={{ fontWeight: 550 }}>{s.name}</b>
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
        <SupplierForm supplier={editing} onClose={() => setEditing(null)} onSave={save} />
      )}
    </>
  )
}
