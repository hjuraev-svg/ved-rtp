import { useMemo, useState } from 'react'
import { api } from '../api'
import { useLiveData, useToast } from '../store'
import type { PayableDeal } from '../types'
import { Field, Modal } from './ui'
import { fmtMoney } from '../util'

const KINDS: Record<string, string> = {
  prepayment: 'Предоплата',
  balance: 'Доплата',
  final: 'Окончательный расчёт',
  refund: 'Возврат',
  other: 'Прочее',
}

/** Создание платежа из раздела «Финансы»: сделка, за что платим, сколько. */
export default function AddPayment({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved: () => void
}) {
  const { notify } = useToast()
  const [q, setQ] = useState('')
  const [dealId, setDealId] = useState<number | null>(null)
  const [form, setForm] = useState({
    direction: 'out',
    status: 'paid',
    kind: 'prepayment',
    amount: '',
    currency: '',
    due_date: '',
    paid_at: new Date().toISOString().slice(0, 10),
    doc_number: '',
  })
  // Сумма инвойса правится здесь же: платёж часто заводят раньше, чем кто-то
  // дошёл до карточки сделки проставить сумму контракта.
  const [invoice, setInvoice] = useState('')
  const [busy, setBusy] = useState(false)

  const { data: deals } = useLiveData<PayableDeal[]>(
    () => api.get(`/api/dashboard/payable${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`),
    [q],
    (e) => e.startsWith('deal') || e.startsWith('item') || e.startsWith('payment'),
  )

  const picked = useMemo(
    () => (deals ?? []).find((d) => d.deal_id === dealId) ?? null,
    [deals, dealId],
  )

  // Когда позиции заведены, сумма контракта считается из них — править её
  // руками бессмысленно: следующее изменение состава всё равно пересчитает.
  const invoiceLocked = !!picked && picked.items.length > 0
  const rest = useMemo(() => {
    if (!picked) return null
    const inv = invoice === '' ? null : Number(invoice)
    if (inv === null || Number.isNaN(inv)) return null
    return inv - Number(picked.paid ?? 0)
  }, [picked, invoice])

  function choose(d: PayableDeal) {
    setDealId(d.deal_id)
    setInvoice(d.invoice_amount ?? '')
    // Валюта и сумма подставляются из сделки: чаще всего гасят остаток целиком.
    setForm((f) => ({
      ...f,
      currency: d.currency,
      amount: d.rest && Number(d.rest) > 0 ? String(d.rest) : f.amount,
    }))
  }

  async function save() {
    if (!dealId) return notify('Выберите сделку', 'err')
    if (!form.amount || Number(form.amount) <= 0) return notify('Укажите сумму платежа', 'err')
    if (form.status === 'paid' && !form.paid_at) return notify('У оплаченного платежа нужна дата', 'err')
    if (form.status === 'planned' && !form.due_date) return notify('У планового платежа нужен срок', 'err')
    setBusy(true)
    try {
      // Сумму инвойса пишем в сделку до платежа: если запись платежа упадёт,
      // сумма всё равно сохранится и вводить её заново не придётся.
      const changed = invoice !== (picked?.invoice_amount ?? '')
      if (!invoiceLocked && changed && invoice !== '') {
        await api.patch(`/api/deals/${dealId}`, {
          contract_amount: Number(invoice),
          currency: form.currency || picked?.currency || 'USD',
        })
      }
      await api.post(`/api/deals/${dealId}/payments`, {
        direction: form.direction,
        status: form.status,
        kind: form.kind,
        amount: Number(form.amount),
        currency: form.currency || 'USD',
        due_date: form.status === 'planned' ? form.due_date : null,
        paid_at: form.status === 'paid' ? form.paid_at : null,
        doc_number: form.doc_number,
      })
      notify('Платёж добавлен')
      onSaved()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось сохранить', 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Новый платёж"
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Отмена</button>
          <button className="btn primary" disabled={busy || !dealId} onClick={save}>
            {busy ? 'Сохранение…' : 'Добавить'}
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Сделка">
          <input
            className="input"
            placeholder="Поиск: код, наименование, поставщик"
            value={q}
            onChange={(e) => { setQ(e.target.value); setDealId(null) }}
          />
        </Field>

        {!picked && (
          <div className="table-wrap" style={{ maxHeight: 210, overflowY: 'auto' }}>
            <table className="data">
              <tbody>
                {(deals ?? []).slice(0, 40).map((d) => (
                  <tr key={d.deal_id} onClick={() => choose(d)}>
                    <td className="mono small faint nowrap">{d.code}</td>
                    <td>{d.title}</td>
                    <td className="small nowrap">{d.supplier}</td>
                    <td className="num nowrap small">
                      {d.invoice_amount
                        ? fmtMoney(d.invoice_amount, d.currency)
                        : <span className="faint">без суммы</span>}
                    </td>
                  </tr>
                ))}
                {(deals ?? []).length === 0 && (
                  <tr><td className="small faint">Ничего не найдено</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {picked && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div className="row" style={{ gap: 8 }}>
              <b>{picked.code}</b>
              <span className="small">{picked.title}</span>
              <div style={{ flex: 1 }} />
              <button className="btn sm" onClick={() => setDealId(null)}>Другая</button>
            </div>
            <div className="row" style={{ gap: 14, marginTop: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <Field label={invoiceLocked ? 'Сумма инвойса (из позиций)' : 'Сумма инвойса'}>
                <input
                  className="input"
                  type="number"
                  step="0.01"
                  style={{ maxWidth: 170 }}
                  value={invoice}
                  disabled={invoiceLocked}
                  placeholder="введите сумму"
                  title={invoiceLocked
                    ? 'Считается из состава поставки — правится во вкладке «Позиции»'
                    : undefined}
                  onChange={(e) => setInvoice(e.target.value)}
                />
              </Field>
              <span className="small">Оплачено: <b>{fmtMoney(picked.paid, picked.currency)}</b></span>
              <span className="small">
                Остаток:{' '}
                <b style={{ color: (rest ?? 0) > 0 ? 'var(--red)' : 'var(--green)' }}>
                  {rest !== null ? fmtMoney(String(rest), form.currency || picked.currency) : '—'}
                </b>
              </span>
              {!invoiceLocked && rest !== null && rest > 0 && (
                <button
                  className="btn sm"
                  onClick={() => setForm((f) => ({ ...f, amount: String(rest) }))}
                >
                  Платёж = остаток
                </button>
              )}
            </div>
            {picked.items.length > 0 ? (
              <div className="small" style={{ marginTop: 8 }}>
                <div className="faint" style={{ marginBottom: 2 }}>За что платим:</div>
                {picked.items.map((i, n) => (
                  <div key={n}>
                    • {i.name}
                    {i.supplier_name && <> · <i>{i.supplier_name}</i></>}
                    {i.qty && <> — {i.qty} {i.unit}</>}
                    {i.amount && <> = {fmtMoney(i.amount, picked.currency)}</>}
                  </div>
                ))}
              </div>
            ) : (
              <div className="small faint" style={{ marginTop: 8 }}>
                Состав не заведён — добавьте позиции во вкладке «Позиции» в карточке сделки.
              </div>
            )}
          </div>
        )}

        <div className="grid-2">
          <Field label="Статус">
            <select className="select" value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="paid">Факт — оплачен</option>
              <option value="planned">План — к оплате</option>
            </select>
          </Field>
          <Field label="Вид">
            <select className="select" value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {Object.entries(KINDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Сумма">
            <input className="input" type="number" step="0.01" value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          </Field>
          <Field label="Валюта">
            <input className="input" value={form.currency} placeholder="USD"
              onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label={form.status === 'paid' ? 'Дата оплаты' : 'Срок оплаты'}>
            <input className="input" type="date"
              value={form.status === 'paid' ? form.paid_at : form.due_date}
              onChange={(e) => setForm(form.status === 'paid'
                ? { ...form, paid_at: e.target.value }
                : { ...form, due_date: e.target.value })} />
          </Field>
          <Field label="Документ / swift">
            <input className="input" value={form.doc_number}
              onChange={(e) => setForm({ ...form, doc_number: e.target.value })} />
          </Field>
        </div>
        <Field label="Направление">
          <select className="select" value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}>
            <option value="out">Платим мы</option>
            <option value="in">Платят нам (выручка по экспорту)</option>
          </select>
        </Field>
      </div>
    </Modal>
  )
}
