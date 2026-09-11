import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Product, Supplier } from '../types'
import { Empty, Field, Loading, Modal } from '../components/ui'

type NewProduct = Omit<Product, 'id' | 'supplier'>

const BLANK: NewProduct = {
  code: '',
  name: '',
  usage: '',
  supplier_id: null,
  is_active: true,
}

export default function Products() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Product | NewProduct | null>(null)
  const [supplierId, setSupplierId] = useState('')
  const [q, setQ] = useState('')

  const { data, reload } = useLiveData<Product[]>(
    () => api.get('/api/products?include_inactive=true'),
    [],
    (e) => e.startsWith('product'),
  )
  const { data: suppliers } = useLiveData<Supplier[]>(
    () => api.get('/api/suppliers'),
    [],
    (e) => e.startsWith('supplier'),
  )

  const shown = useMemo(() => {
    let rows = data ?? []
    if (supplierId) {
      rows =
        supplierId === 'none'
          ? rows.filter((p) => !p.supplier_id)
          : rows.filter((p) => String(p.supplier_id) === supplierId)
    }
    const needle = q.trim().toLowerCase()
    if (needle) {
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(needle) ||
          p.code.toLowerCase().includes(needle) ||
          p.usage.toLowerCase().includes(needle),
      )
    }
    return rows
  }, [data, supplierId, q])

  async function save(form: Product | NewProduct) {
    if (!form.name.trim()) return notify('Укажите наименование', 'err')
    try {
      const body = { ...form, name: form.name.trim(), code: form.code.trim() }
      if ('id' in form) await api.patch(`/api/products/${form.id}`, body)
      else await api.post('/api/products', body)
      notify('Сохранено')
      setEditing(null)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  async function remove(product: Product) {
    try {
      await api.del(`/api/products/${product.id}`)
      notify('Позиция удалена')
      setEditing(null)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось удалить', 'err')
    }
  }

  if (!data) return <Loading />

  return (
    <>
      <div className="filters">
        <input
          className="input grow"
          placeholder="Поиск: наименование, код, назначение"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="select"
          value={supplierId}
          onChange={(e) => setSupplierId(e.target.value)}
        >
          <option value="">Все поставщики</option>
          <option value="none">Без поставщика</option>
          {(suppliers ?? []).map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.name}
            </option>
          ))}
        </select>
        <span className="small faint nowrap">
          {shown.length} из {data.length}
        </span>
        {canEdit && (
          <button className="btn primary" onClick={() => setEditing({ ...BLANK })}>
            + Продукция
          </button>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="card">
          <Empty
            text={
              data.length === 0
                ? 'Продукция пока не заведена. Нажмите «+ Продукция».'
                : 'Под выбранный фильтр продукция не подходит.'
            }
          />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Код</th>
                <th>Наименование</th>
                <th>Для чего используется</th>
                <th>Поставщик</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.id} onClick={() => canEdit && setEditing(p)}>
                  <td className="mono faint nowrap">{p.code || '—'}</td>
                  <td>
                    <b style={{ fontWeight: 550 }}>{p.name}</b>
                  </td>
                  <td className="small" style={{ maxWidth: 420 }}>
                    {p.usage || '—'}
                  </td>
                  <td className="nowrap">{p.supplier?.name ?? '—'}</td>
                  <td>
                    <span className={`badge ${p.is_active ? 'green' : ''}`}>
                      {p.is_active ? 'Активна' : 'Архив'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <ProductForm
          product={editing}
          suppliers={suppliers ?? []}
          onClose={() => setEditing(null)}
          onSave={save}
          onDelete={'id' in editing ? () => remove(editing as Product) : undefined}
        />
      )}
    </>
  )
}

function ProductForm({
  product,
  suppliers,
  onClose,
  onSave,
  onDelete,
}: {
  product: Product | NewProduct
  suppliers: Supplier[]
  onClose: () => void
  onSave: (p: Product | NewProduct) => void
  onDelete?: () => void
}) {
  const [form, setForm] = useState(product)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      title={'id' in product ? 'Позиция номенклатуры' : 'Новая продукция'}
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end', width: '100%' }}>
          {onDelete && (
            <button
              className="btn danger"
              style={{ marginRight: 'auto' }}
              onClick={() => setConfirmDelete(true)}
            >
              🗑 Удалить
            </button>
          )}
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={() => onSave(form)}>
            Сохранить
          </button>
        </div>
      }
    >
      {confirmDelete ? (
        <>
          <p style={{ marginTop: 0 }}>
            Удалить позицию «{form.name}» из номенклатуры? Действие необратимо.
          </p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={() => setConfirmDelete(false)}>
              Отмена
            </button>
            <button className="btn danger" onClick={onDelete}>
              Удалить
            </button>
          </div>
        </>
      ) : (
        <div style={{ display: 'grid', gap: 13 }}>
          <div className="grid-2">
            <Field label="Код продукции">
              <input
                className="input mono"
                value={form.code}
                placeholder="JNS-PRF-001"
                onChange={(e) => set('code', e.target.value)}
              />
            </Field>
            <Field label="Поставщик">
              <select
                className="select"
                value={form.supplier_id === null ? '' : String(form.supplier_id)}
                onChange={(e) => set('supplier_id', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— не указан —</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={String(s.id)}>
                    {s.name}
                    {s.category ? ` · ${s.category}` : ''}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Наименование">
            <input
              className="input"
              value={form.name}
              autoFocus
              placeholder="Отдушка для геля, парфюмерная композиция"
              onChange={(e) => set('name', e.target.value)}
            />
          </Field>
          <Field label="Для чего используется">
            <textarea
              className="textarea"
              rows={4}
              value={form.usage}
              placeholder="В каком продукте и на каком участке применяется"
              onChange={(e) => set('usage', e.target.value)}
            />
          </Field>
          <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={form.is_active}
              style={{ width: 16, height: 16, accentColor: 'var(--green)' }}
              onChange={(e) => set('is_active', e.target.checked)}
            />
            <span className="small">Активна</span>
          </label>
        </div>
      )}
    </Modal>
  )
}
