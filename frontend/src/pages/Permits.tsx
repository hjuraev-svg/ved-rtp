import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Permit, Product, Supplier } from '../types'
import { Empty, Field, Loading, Modal } from '../components/ui'
import { fmtDate } from '../util'

type NewPermit = Omit<Permit, 'id' | 'product' | 'supplier' | 'file_name' | 'days_left'>

const BLANK: NewPermit = {
  kind: '', name: '', number: '', authority: '',
  issued_at: null, valid_until: null,
  product_id: null, supplier_id: null, note: '', is_active: true,
}

const KINDS = [
  'Регистрационное удостоверение',
  'Сертификат соответствия',
  'Санитарно-эпидемиологическое заключение',
  'Сертификат качества',
  'Декларация о соответствии',
  'Лицензия',
]

/** Порог «скоро истекает». 60 дней — продление обычно занимает не меньше. */
const SOON_DAYS = 60

export default function Permits() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Permit | NewPermit | null>(null)
  const [filter, setFilter] = useState<'all' | 'soon' | 'expired'>('all')
  const [q, setQ] = useState('')

  const { data, reload } = useLiveData<Permit[]>(
    () => api.get('/api/permits?include_inactive=true'),
    [],
    (e) => e.startsWith('permit'),
  )
  const { data: products } = useLiveData<Product[]>(() => api.get('/api/products'), [])
  const { data: suppliers } = useLiveData<Supplier[]>(() => api.get('/api/suppliers'), [])

  const counts = useMemo(() => {
    const rows = data ?? []
    return {
      all: rows.length,
      soon: rows.filter((p) => p.days_left !== null && p.days_left >= 0 && p.days_left <= SOON_DAYS).length,
      expired: rows.filter((p) => p.days_left !== null && p.days_left < 0).length,
    }
  }, [data])

  const shown = useMemo(() => {
    let rows = data ?? []
    if (filter === 'soon') rows = rows.filter((p) => p.days_left !== null && p.days_left >= 0 && p.days_left <= SOON_DAYS)
    if (filter === 'expired') rows = rows.filter((p) => p.days_left !== null && p.days_left < 0)
    const needle = q.trim().toLowerCase()
    if (needle) {
      rows = rows.filter((p) =>
        p.name.toLowerCase().includes(needle) ||
        p.number.toLowerCase().includes(needle) ||
        p.kind.toLowerCase().includes(needle))
    }
    return rows
  }, [data, filter, q])

  async function save(form: Permit | NewPermit) {
    if (!form.name.trim()) return notify('Укажите наименование документа', 'err')
    try {
      const body = { ...form, name: form.name.trim() }
      if ('id' in form) await api.patch(`/api/permits/${form.id}`, body)
      else await api.post('/api/permits', body)
      notify('Сохранено'); setEditing(null); reload()
    } catch (e: any) { notify(e?.message ?? 'Ошибка', 'err') }
  }

  async function remove(p: Permit) {
    try { await api.del(`/api/permits/${p.id}`); notify('Удалено'); setEditing(null); reload() }
    catch (e: any) { notify(e?.message ?? 'Не удалось удалить', 'err') }
  }

  if (!data) return <Loading />

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="tabs">
          <button className={`tab ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
            Все · {counts.all}
          </button>
          <button className={`tab ${filter === 'soon' ? 'active' : ''}`} onClick={() => setFilter('soon')}>
            Истекают за {SOON_DAYS} дней · {counts.soon}
          </button>
          <button className={`tab ${filter === 'expired' ? 'active' : ''}`} onClick={() => setFilter('expired')}>
            Просрочены · {counts.expired}
          </button>
        </div>
      </div>

      <div className="filters">
        <input className="input grow" placeholder="Поиск: наименование, номер, вид"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="small faint nowrap">{shown.length} из {data.length}</span>
        {canEdit && (
          <button className="btn primary" onClick={() => setEditing({ ...BLANK })}>+ Документ</button>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="card">
          <Empty text={data.length === 0
            ? 'Реестр пуст. Заведите рег. удостоверения и сертификаты — система будет следить за сроками.'
            : 'Под выбранный фильтр документы не подходят.'} />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Документ</th>
                <th>Вид</th>
                <th>Номер</th>
                <th>Продукция</th>
                <th>Действует до</th>
                <th>Осталось</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => {
                const d = p.days_left
                const cls = d === null ? '' : d < 0 ? 'red' : d <= SOON_DAYS ? 'amber' : 'green'
                return (
                  <tr key={p.id} onClick={() => canEdit && setEditing(p)}>
                    <td><b style={{ fontWeight: 550 }}>{p.name}</b></td>
                    <td className="small">{p.kind || '—'}</td>
                    <td className="mono small faint">{p.number || '—'}</td>
                    <td className="small">{p.product?.name ?? '—'}</td>
                    <td className="nowrap">{fmtDate(p.valid_until) || 'бессрочно'}</td>
                    <td className="nowrap">
                      {d === null ? <span className="faint">—</span> : (
                        <span className={`badge ${cls}`}>
                          {d < 0 ? `просрочен на ${-d} дн.` : `${d} дн.`}
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <PermitForm
          permit={editing}
          products={products ?? []}
          suppliers={suppliers ?? []}
          onClose={() => setEditing(null)}
          onSave={save}
          onDelete={'id' in editing ? () => remove(editing as Permit) : undefined}
        />
      )}
    </>
  )
}

function PermitForm({
  permit, products, suppliers, onClose, onSave, onDelete,
}: {
  permit: Permit | NewPermit
  products: Product[]
  suppliers: Supplier[]
  onClose: () => void
  onSave: (p: Permit | NewPermit) => void
  onDelete?: () => void
}) {
  const [form, setForm] = useState(permit)
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      title={'id' in permit ? 'Разрешительный документ' : 'Новый документ'}
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end', width: '100%' }}>
          {onDelete && (
            <button className="btn danger" style={{ marginRight: 'auto' }} onClick={onDelete}>
              🗑 Удалить
            </button>
          )}
          <button className="btn" onClick={onClose}>Отмена</button>
          <button className="btn primary" onClick={() => onSave(form)}>Сохранить</button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Наименование">
          <input className="input" value={form.name} autoFocus
            placeholder="Регистрационное удостоверение на презервативы SOFT"
            onChange={(e) => set('name', e.target.value)} />
        </Field>
        <div className="grid-2">
          <Field label="Вид">
            <input className="input" value={form.kind} list="permit-kinds"
              onChange={(e) => set('kind', e.target.value)} />
            <datalist id="permit-kinds">
              {KINDS.map((k) => <option key={k} value={k} />)}
            </datalist>
          </Field>
          <Field label="Номер">
            <input className="input mono" value={form.number}
              onChange={(e) => set('number', e.target.value)} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Выдан">
            <input className="input" type="date" value={form.issued_at ?? ''}
              onChange={(e) => set('issued_at', e.target.value || null)} />
          </Field>
          <Field label="Действует до (пусто = бессрочно)">
            <input className="input" type="date" value={form.valid_until ?? ''}
              onChange={(e) => set('valid_until', e.target.value || null)} />
          </Field>
        </div>
        <Field label="Кем выдан">
          <input className="input" value={form.authority}
            onChange={(e) => set('authority', e.target.value)} />
        </Field>
        <div className="grid-2">
          <Field label="Продукция">
            <select className="select" value={form.product_id === null ? '' : String(form.product_id)}
              onChange={(e) => set('product_id', e.target.value ? Number(e.target.value) : null)}>
              <option value="">— не указана —</option>
              {products.map((p) => (
                <option key={p.id} value={String(p.id)}>{p.code ? `${p.code} · ` : ''}{p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Поставщик">
            <select className="select" value={form.supplier_id === null ? '' : String(form.supplier_id)}
              onChange={(e) => set('supplier_id', e.target.value ? Number(e.target.value) : null)}>
              <option value="">— не указан —</option>
              {suppliers.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Примечание">
          <textarea className="textarea" rows={3} value={form.note}
            onChange={(e) => set('note', e.target.value)} />
        </Field>
        <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={form.is_active}
            style={{ width: 16, height: 16, accentColor: 'var(--green)' }}
            onChange={(e) => set('is_active', e.target.checked)} />
          <span className="small">Действующий</span>
        </label>
      </div>
    </Modal>
  )
}
