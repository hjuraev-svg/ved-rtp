import { useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { FinanceRecord } from '../types'
import { Empty, Field, Loading, Modal } from '../components/ui'
import SupplierPicker from '../components/SupplierPicker'
import { fmtDate, fmtMoney } from '../util'

type Form = {
  id?: number
  supplier_id: number | null
  product_name: string
  quantity: string
  unit: string
  invoice_number: string
  invoice_amount: string
  currency: string
  payment_terms: string
  paid_amount: string
  due_date: string
  note: string
}

const BLANK: Form = {
  supplier_id: null, product_name: '', quantity: '', unit: 'шт', invoice_number: '',
  invoice_amount: '', currency: 'USD', payment_terms: '', paid_amount: '0', due_date: '', note: '',
}

const UNITS = ['шт', 'кг', 'т', 'л']
const CURRENCIES = ['USD', 'EUR', 'CNY', 'RUB', 'UZS']

export const LEDGER_STATUS: Record<FinanceRecord['status'], { label: string; cls: string }> = {
  paid: { label: 'Оплачено', cls: 'green' },
  partial: { label: 'Частично оплачено', cls: 'amber' },
  unpaid: { label: 'Не оплачено', cls: 'blue' },
  overdue: { label: 'Просрочено', cls: 'red' },
}

export default function Ledger() {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Form | null>(null)
  const [filter, setFilter] = useState<'all' | FinanceRecord['status']>('all')
  const [q, setQ] = useState('')

  const { data, reload } = useLiveData<FinanceRecord[]>(
    () => api.get('/api/ledger'),
    [],
    (e) => e.startsWith('ledger') || e.startsWith('supplier'),
  )

  const shown = useMemo(() => {
    let rows = data ?? []
    if (filter !== 'all') rows = rows.filter((r) => r.status === filter)
    const needle = q.trim().toLowerCase()
    if (needle) {
      rows = rows.filter((r) =>
        r.supplier_name.toLowerCase().includes(needle) ||
        r.product_name.toLowerCase().includes(needle) ||
        r.invoice_number.toLowerCase().includes(needle))
    }
    return rows
  }, [data, filter, q])

  function edit(r: FinanceRecord) {
    setEditing({
      id: r.id,
      supplier_id: r.supplier_id,
      product_name: r.product_name,
      quantity: r.quantity ?? '',
      unit: r.unit,
      invoice_number: r.invoice_number,
      invoice_amount: r.invoice_amount,
      currency: r.currency,
      payment_terms: r.payment_terms,
      paid_amount: r.paid_amount,
      due_date: r.due_date ?? '',
      note: r.note,
    })
  }

  async function save(f: Form) {
    if (!f.supplier_id) return notify('Выберите поставщика', 'err')
    if (!f.product_name.trim()) return notify('Укажите наименование продукта', 'err')
    if (f.invoice_amount === '' || Number(f.invoice_amount) < 0) return notify('Укажите сумму инвойса', 'err')
    const body = {
      supplier_id: f.supplier_id,
      product_name: f.product_name.trim(),
      quantity: f.quantity === '' ? null : f.quantity,
      unit: f.unit,
      invoice_number: f.invoice_number.trim(),
      invoice_amount: f.invoice_amount,
      currency: (f.currency || 'USD').toUpperCase(),
      payment_terms: f.payment_terms.trim(),
      paid_amount: f.paid_amount === '' ? '0' : f.paid_amount,
      due_date: f.due_date || null,
      note: f.note,
    }
    try {
      if (f.id) await api.patch(`/api/ledger/${f.id}`, body)
      else await api.post('/api/ledger', body)
      notify('Сохранено'); setEditing(null); reload()
    } catch (e: any) { notify(e?.message ?? 'Ошибка', 'err') }
  }

  async function remove(id: number) {
    if (!confirm('Удалить запись из реестра?')) return
    try { await api.del(`/api/ledger/${id}`); notify('Удалено'); setEditing(null); reload() }
    catch (e: any) { notify(e?.message ?? 'Не удалось удалить', 'err') }
  }

  if (!data) return <Loading />

  const count = (s: FinanceRecord['status']) => data.filter((r) => r.status === s).length

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="tabs">
          <button className={`tab ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
            Все · {data.length}
          </button>
          {(Object.keys(LEDGER_STATUS) as FinanceRecord['status'][]).map((s) => (
            <button key={s} className={`tab ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
              {LEDGER_STATUS[s].label} · {count(s)}
            </button>
          ))}
        </div>
      </div>

      <div className="filters">
        <input className="input grow" placeholder="Поиск: поставщик, продукт, № инвойса"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="small faint nowrap">{shown.length} из {data.length}</span>
        {canEdit && (
          <button className="btn primary" onClick={() => setEditing({ ...BLANK })}>+ Запись</button>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="card">
          <Empty text={data.length === 0
            ? 'Реестр пуст. Внесите инвойс поставщика — долг и статус посчитаются сами.'
            : 'Под выбранный фильтр записи не подходят.'} />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Поставщик</th>
                <th>Наименование продукта</th>
                <th>Кол-во</th>
                <th>Сумма инвойса</th>
                <th>Условия оплаты</th>
                <th>Оплачено</th>
                <th>Долг</th>
                <th>Срок оплаты</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const st = LEDGER_STATUS[r.status]
                return (
                  <tr key={r.id} onClick={() => canEdit && edit(r)}>
                    <td><b style={{ fontWeight: 550 }}>{r.supplier_name}</b></td>
                    <td className="small">
                      {r.product_name}
                      {r.invoice_number && <div className="mono faint">{r.invoice_number}</div>}
                    </td>
                    <td className="nowrap num">
                      {r.quantity !== null ? `${Number(r.quantity).toLocaleString('ru-RU')} ${r.unit}` : '—'}
                    </td>
                    <td className="nowrap num">{fmtMoney(r.invoice_amount, r.currency)}</td>
                    <td className="small">{r.payment_terms || '—'}</td>
                    <td className="nowrap num">{fmtMoney(r.paid_amount, r.currency)}</td>
                    <td className="nowrap num">
                      <b style={{ fontWeight: 600 }}>{fmtMoney(r.debt, r.currency)}</b>
                    </td>
                    <td className="nowrap">{fmtDate(r.due_date)}</td>
                    <td className="nowrap">
                      <span className={`badge ${st.cls}`}>
                        {st.label}
                        {r.days_overdue ? ` · ${r.days_overdue} дн.` : ''}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <RecordForm
          initial={editing}
          onClose={() => setEditing(null)}
          onSave={save}
          onDelete={editing.id ? () => remove(editing.id!) : undefined}
        />
      )}
    </>
  )
}

function RecordForm({
  initial, onClose, onSave, onDelete,
}: {
  initial: Form
  onClose: () => void
  onSave: (f: Form) => void
  onDelete?: () => void
}) {
  const [form, setForm] = useState(initial)
  const set = (k: keyof Form, v: any) => setForm((f) => ({ ...f, [k]: v }))
  const debt = (Number(form.invoice_amount) || 0) - (Number(form.paid_amount) || 0)

  return (
    <Modal
      title={initial.id ? 'Запись реестра' : 'Новая запись'}
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
        <Field label="Поставщик">
          <SupplierPicker value={form.supplier_id} onChange={(id) => set('supplier_id', id)} />
        </Field>
        <Field label="Наименование продукта">
          <input className="input" value={form.product_name} autoFocus
            onChange={(e) => set('product_name', e.target.value)} />
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 2fr', gap: 10 }}>
          <Field label="Кол-во">
            <input className="input" type="number" min="0" step="any" value={form.quantity}
              onChange={(e) => set('quantity', e.target.value)} />
          </Field>
          <Field label="Ед.">
            <select className="select" value={form.unit} onChange={(e) => set('unit', e.target.value)}>
              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label="№ инвойса">
            <input className="input" value={form.invoice_number}
              onChange={(e) => set('invoice_number', e.target.value)} />
          </Field>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
          <Field label="Сумма инвойса">
            <input className="input" type="number" min="0" step="0.01" value={form.invoice_amount}
              onChange={(e) => set('invoice_amount', e.target.value)} />
          </Field>
          <Field label="Валюта">
            <input className="input" list="ledger-currencies" value={form.currency}
              onChange={(e) => set('currency', e.target.value)} />
            <datalist id="ledger-currencies">
              {CURRENCIES.map((c) => <option key={c} value={c} />)}
            </datalist>
          </Field>
        </div>
        <Field label="Условия оплаты">
          <input className="input" value={form.payment_terms}
            placeholder="30% предоплата / 70% по факту отгрузки"
            onChange={(e) => set('payment_terms', e.target.value)} />
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Сумма оплаченная">
            <input className="input" type="number" min="0" step="0.01" value={form.paid_amount}
              onChange={(e) => set('paid_amount', e.target.value)} />
          </Field>
          <Field label="Срок оплаты">
            <input className="input" type="date" value={form.due_date}
              onChange={(e) => set('due_date', e.target.value)} />
          </Field>
        </div>
        <div className="small">
          Долг: <b>{fmtMoney(debt, form.currency || 'USD')}</b>
          <span className="faint"> · статус посчитается сам по долгу и сроку оплаты</span>
        </div>
        <Field label="Примечание">
          <textarea className="input" rows={2} value={form.note}
            onChange={(e) => set('note', e.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}
