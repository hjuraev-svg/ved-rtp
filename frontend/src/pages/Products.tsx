import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Product, Supplier } from '../types'
import { Empty, Field, Loading, Modal } from '../components/ui'

type NewProduct = Omit<Product, 'id' | 'supplier'>

const BLANK: NewProduct = {
  code: '',
  supplier_code: '',
  name: '',
  kind: '',
  unit: '',
  usage: '',
  supplier_id: null,
  is_active: true,
}

const NO_KIND = '—'
/** Offered in the form; the field stays free text so an unforeseen type fits. */
const KIND_SUGGESTIONS = [
  'Сырьё',
  'Упаковка',
  'Готовая продукция',
  'Оборудование',
  'Запчасти',
  'Прочее',
]
const UNIT_SUGGESTIONS = ['кг', 'г', 'л', 'мл', 'шт', 'упак', 'м', 'м²', 'рул']

export default function Products() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Product | NewProduct | null>(null)
  const [supplierId, setSupplierId] = useState('')
  const [kind, setKind] = useState('')
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

  // Tab counts come from the whole list, so labels stay put while filtering.
  const kinds = useMemo(() => {
    const counts = new Map<string, number>()
    for (const p of data ?? []) {
      const key = p.kind || NO_KIND
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) =>
      a[0] === NO_KIND ? 1 : b[0] === NO_KIND ? -1 : b[1] - a[1],
    )
  }, [data])

  const shown = useMemo(() => {
    let rows = data ?? []
    if (kind) rows = rows.filter((p) => (p.kind || NO_KIND) === kind)
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
          p.supplier_code.toLowerCase().includes(needle) ||
          p.usage.toLowerCase().includes(needle),
      )
    }
    return rows
  }, [data, kind, supplierId, q])

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
      {kinds.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="tabs">
            <button className={`tab ${kind === '' ? 'active' : ''}`} onClick={() => setKind('')}>
              Все · {data.length}
            </button>
            {kinds.map(([name, count]) => (
              <button
                key={name}
                className={`tab ${kind === name ? 'active' : ''}`}
                onClick={() => setKind(name)}
              >
                {name === NO_KIND ? 'Без типа' : name} · {count}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="filters">
        <input
          className="input grow"
          placeholder="Поиск: наименование, код, артикул, назначение"
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
                <th>Тип</th>
                <th className="num">Ед.</th>
                <th>Для чего используется</th>
                <th>Поставщик</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.id} onClick={() => canEdit && setEditing(p)}>
                  <td className="mono faint nowrap">
                    {p.code || '—'}
                    {p.supplier_code && (
                      <div className="small faint">{p.supplier_code}</div>
                    )}
                  </td>
                  <td>
                    <b style={{ fontWeight: 550 }}>{p.name}</b>
                  </td>
                  <td className="nowrap">
                    {p.kind ? <span className="badge">{p.kind}</span> : '—'}
                  </td>
                  <td className="num nowrap faint">{p.unit || '—'}</td>
                  <td className="small" style={{ maxWidth: 380 }}>
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
                placeholder="JNS 101"
                onChange={(e) => set('code', e.target.value)}
              />
            </Field>
            <Field label="Артикул поставщика">
              <input
                className="input mono"
                value={form.supplier_code}
                placeholder="код в прайсе поставщика"
                onChange={(e) => set('supplier_code', e.target.value)}
              />
            </Field>
          </div>
          <div className="grid-2">
            <Field label="Тип">
              <input
                className="input"
                value={form.kind}
                list="product-kinds"
                placeholder="Сырьё"
                onChange={(e) => set('kind', e.target.value)}
              />
              <datalist id="product-kinds">
                {KIND_SUGGESTIONS.map((k) => (
                  <option key={k} value={k} />
                ))}
              </datalist>
            </Field>
            <Field label="Единица измерения">
              <input
                className="input"
                value={form.unit}
                list="product-units"
                placeholder="кг"
                onChange={(e) => set('unit', e.target.value)}
              />
              <datalist id="product-units">
                {UNIT_SUGGESTIONS.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </Field>
          </div>
          <div className="grid-2">
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
