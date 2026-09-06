import { useEffect, useMemo, useState } from 'react'
import { api, apiUrl, getToken } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type {
  Claim,
  Comment,
  Deal,
  DocumentItem,
  ChecklistItem,
  HistoryEvent,
  Quote,
  Stage,
  Supplier,
} from '../types'
import { Empty, ErrorBox, Field, Loading, Modal, Panel, Progress } from '../components/ui'
import SupplierPicker from '../components/SupplierPicker'
import {
  CLAIM_STATUS_LABELS,
  PACKING_LABELS,
  PRIORITY_LABELS,
  REASON_LABELS,
  PIPELINE_LABELS,
  STATUS_LABELS,
  TRANSPORT_LABELS,
  dateInput,
  days,
  fmtDate,
  fmtDateTime,
  fmtMoney,
} from '../util'

type Tab = 'overview' | 'checklist' | 'docs' | 'quotes' | 'claims' | 'history'

export default function DealDetail({
  dealId,
  navigate,
}: {
  dealId: number
  navigate: (p: string) => void
}) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const [moving, setMoving] = useState<number | null>(null)

  const {
    data: deal,
    error,
    loading,
    reload,
  } = useLiveData<Deal>(() => api.get(`/api/deals/${dealId}`), [dealId])
  const { data: stages } = useLiveData<Stage[]>(
    () => api.get(`/api/stages?pipeline=${deal?.pipeline ?? 'import'}`),
    [deal?.pipeline],
  )

  if (loading && !deal) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!deal || !stages) return null

  async function move(stageId: number, comment: string) {
    try {
      await api.post(`/api/deals/${dealId}/move`, { stage_id: stageId, comment })
      notify(`Переведено на этап ${stageId}`)
      setMoving(null)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось перевести', 'err')
    }
  }

  const idx = stages.findIndex((s) => s.id === deal.stage_id)
  const nextStage = idx >= 0 && idx < stages.length - 1 ? stages[idx + 1].id : null

  return (
    <>
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <button className="btn ghost sm" onClick={() => navigate('deals')}>
          ← Все сделки
        </button>
        <span className="mono faint">{deal.code}</span>
        <span className="badge blue">{PIPELINE_LABELS[deal.pipeline] ?? deal.pipeline}</span>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 640, letterSpacing: '-0.02em' }}>
          {deal.title}
        </h2>
        <span className="badge">{STATUS_LABELS[deal.status] ?? deal.status}</span>
        {deal.priority !== 'normal' && (
          <span className="badge amber">{PRIORITY_LABELS[deal.priority]}</span>
        )}
        {deal.is_overdue && <span className="badge red">🔴 Красная зона</span>}
        <div style={{ flex: 1 }} />
        {canEdit && nextStage && (
          <button className="btn primary" onClick={() => setMoving(nextStage)}>
            Следующий этап →
          </button>
        )}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="stepper">
          {stages.map((s, i) => (
            <button
              key={s.id}
              className={`step ${s.id === deal.stage_id ? 'current' : i < idx ? 'done' : ''}`}
              onClick={() => canEdit && setMoving(s.id)}
              disabled={!canEdit}
              title={s.description}
            >
              <b>{i + 1}</b>
              {s.name}
            </button>
          ))}
        </div>
        <div
          className="row wrap"
          style={{ padding: '10px 15px', borderTop: '1px solid var(--border)', gap: 14 }}
        >
          <span className="small">
            На этапе: <b className={deal.is_overdue ? 'badge red' : ''}>{days(deal.days_in_stage)}</b>
            {deal.sla_days !== null && <span className="faint"> из {deal.sla_days} по нормативу</span>}
          </span>
          <span className="small faint">с {fmtDateTime(deal.stage_entered_at)}</span>
          <div style={{ flex: 1 }} />
          <span className="small faint">Документы</span>
          <div style={{ width: 110 }}>
            <Progress pct={deal.docs_ready_pct} label />
          </div>
          <span className="small faint">Чек-лист</span>
          <div style={{ width: 110 }}>
            <Progress pct={deal.checklist_done_pct} label />
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="tabs">
          {(
            [
              ['overview', 'Карточка'],
              ['checklist', 'Чек-лист'],
              ['docs', 'Документы'],
              ['quotes', 'КП'],
              ['claims', 'Претензии'],
              ['history', 'История'],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              className={`tab ${tab === key ? 'active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview' && <Overview deal={deal} onSaved={reload} />}
      {tab === 'checklist' && <Checklist dealId={dealId} currentStage={deal.stage_id} />}
      {tab === 'docs' && <Documents dealId={dealId} />}
      {tab === 'quotes' && <Quotes dealId={dealId} onChanged={reload} />}
      {tab === 'claims' && <Claims dealId={dealId} />}
      {tab === 'history' && <History dealId={dealId} />}

      {moving !== null && (
        <MoveModal
          stage={stages.find((s) => s.id === moving)!}
          onClose={() => setMoving(null)}
          onConfirm={(comment) => move(moving, comment)}
        />
      )}
    </>
  )
}

// ------------------------------------------------------------------ overview
function Overview({ deal, onSaved }: { deal: Deal; onSaved: () => void }) {
  const isImport = deal.pipeline === 'import'
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [form, setForm] = useState<Record<string, any>>({})
  const [busy, setBusy] = useState(false)
  const [pendingPipeline, setPendingPipeline] = useState<string | null>(null)
  const [changingPipeline, setChangingPipeline] = useState(false)
  useEffect(() => setForm({}), [deal.id, deal.updated_at])

  const value = (key: keyof Deal) => (key in form ? form[key] : (deal[key] ?? ''))
  const set = (key: string, v: any) => setForm((f) => ({ ...f, [key]: v }))
  const dirty = Object.keys(form).length > 0

  async function save() {
    setBusy(true)
    try {
      const payload: Record<string, any> = {}
      for (const [k, v] of Object.entries(form)) payload[k] = v === '' ? null : v
      // Text columns are non-nullable — send an empty string instead of null.
      for (const k of [
        'title', 'description', 'requester', 'country', 'incoterms', 'contract_number',
        'unk_number', 'gtd_number', 'act_number', 'transport_mode', 'packing_status', 'currency',
      ]) {
        if (k in payload && payload[k] === null) payload[k] = ''
      }
      await api.patch(`/api/deals/${deal.id}`, payload)
      notify('Сохранено')
      setForm({})
      onSaved()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось сохранить', 'err')
    } finally {
      setBusy(false)
    }
  }

  async function changePipeline() {
    if (!pendingPipeline || pendingPipeline === deal.pipeline) return
    setChangingPipeline(true)
    try {
      await api.patch(`/api/deals/${deal.id}/pipeline`, { pipeline: pendingPipeline })
      notify(`Тип сделки изменён на «${PIPELINE_LABELS[pendingPipeline]}»`)
      setPendingPipeline(null)
      onSaved()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось изменить тип сделки', 'err')
    } finally {
      setChangingPipeline(false)
    }
  }

  const ro = !canEdit
  const text = (key: keyof Deal, label: string, placeholder = '') => (
    <Field label={label}>
      <input
        className="input"
        value={value(key) as string}
        placeholder={placeholder}
        disabled={ro}
        onChange={(e) => set(key as string, e.target.value)}
      />
    </Field>
  )
  const date = (key: keyof Deal, label: string) => (
    <Field label={label}>
      <input
        className="input"
        type="date"
        value={dateInput(value(key) as string)}
        disabled={ro}
        onChange={(e) => set(key as string, e.target.value || null)}
      />
    </Field>
  )
  const num = (key: keyof Deal, label: string) => (
    <Field label={label}>
      <input
        className="input"
        type="number"
        value={(value(key) as string) ?? ''}
        disabled={ro}
        onChange={(e) => set(key as string, e.target.value === '' ? null : e.target.value)}
      />
    </Field>
  )

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {dirty && (
        <div className="card" style={{ padding: '11px 15px' }}>
          <div className="row">
            <span className="small">Есть несохранённые изменения</span>
            <div style={{ flex: 1 }} />
            <button className="btn sm" onClick={() => setForm({})}>
              Сбросить
            </button>
            <button className="btn primary sm" onClick={save} disabled={busy}>
              {busy ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </div>
      )}

      <Panel title="Общее">
        <div className="kv">
          <Field label="Тип сделки">
            <select
              className="select"
              value={deal.pipeline}
              disabled={ro || dirty}
              title={dirty ? 'Сначала сохраните или сбросьте остальные изменения' : undefined}
              onChange={(e) => setPendingPipeline(e.target.value)}
            >
              {Object.entries(PIPELINE_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {text('title', 'Наименование')}
          {text('requester', 'Заявитель')}
          <Field label="Статус">
            <select
              className="select"
              value={value('status') as string}
              disabled={ro}
              onChange={(e) => set('status', e.target.value)}
            >
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Приоритет">
            <select
              className="select"
              value={value('priority') as string}
              disabled={ro}
              onChange={(e) => set('priority', e.target.value)}
            >
              {Object.entries(PRIORITY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Поставщик">
            <SupplierPicker
              value={(value('supplier_id') as number | null) || null}
              disabled={ro}
              onChange={(id) => set('supplier_id', id)}
            />
          </Field>
          {text('country', 'Страна')}
          {text('incoterms', 'Инкотермс', 'FOB / CIF / EXW / DAP')}
        </div>
        <div className="mt">
          <Field label="Описание">
            <textarea
              className="textarea"
              value={value('description') as string}
              disabled={ro}
              onChange={(e) => set('description', e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      {pendingPipeline && pendingPipeline !== deal.pipeline && (
        <Modal
          title="Изменить тип сделки?"
          onClose={() => setPendingPipeline(null)}
          footer={
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button
                className="btn"
                onClick={() => setPendingPipeline(null)}
                disabled={changingPipeline}
              >
                Отмена
              </button>
              <button className="btn primary" onClick={changePipeline} disabled={changingPipeline}>
                {changingPipeline ? 'Изменение…' : 'Изменить тип'}
              </button>
            </div>
          }
        >
          <p style={{ margin: 0 }}>
            Сделка перейдёт с типа «{PIPELINE_LABELS[deal.pipeline]}» на «
            {PIPELINE_LABELS[pendingPipeline]}».
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Код сделки и маршрут этапов изменятся. Сделка будет установлена на первый этап нового
            типа. Старые отметки чек-листа и загруженные документы сохранятся и снова появятся, если
            вернуть прежний тип.
          </p>
        </Modal>
      )}

      {isImport && (
      <Panel title="Блоки 5–8 · Контракт, валютный контроль, оплата">
        <div className="kv">
          {text('contract_number', 'Контракт №')}
          {date('contract_date', 'Дата контракта')}
          {num('contract_amount', 'Сумма контракта')}
          {text('currency', 'Валюта')}
          {text('unk_number', 'УНК (банк)')}
          {date('unk_date', 'Дата регистрации УНК')}
          {date('payment_confirmed_at', 'Оплата подтверждена')}
          {num('payment_amount', 'Сумма оплаты')}
          {date('order_confirmation_at', 'Order Confirmation получен')}
        </div>
        {!deal.unk_number && deal.contract_number && (
          <div className="error-box mt">
            Контракт подписан, но УНК в банке не зарегистрирован — риск нарушения сроков валютного
            законодательства.
          </div>
        )}
      </Panel>
      )}

      {!isImport && (
        <Panel title="Договор и оплата">
          <div className="kv">
            {text('contract_number', 'Договор / счёт №')}
            {date('contract_date', 'Дата договора')}
            {num('contract_amount', 'Сумма')}
            {text('currency', 'Валюта')}
            {date('payment_confirmed_at', 'Оплата подтверждена')}
            {num('payment_amount', 'Сумма оплаты')}
          </div>
        </Panel>
      )}

      {isImport && (
      <Panel title="Блоки 9–12 · Производство, упаковка, фрахт, транзит">
        <div className="kv">
          {date('production_ready_plan', 'Готовность — план')}
          {date('production_ready_fact', 'Готовность — факт')}
          <Field label="Упаковка / маркировка">
            <select
              className="select"
              value={value('packing_status') as string}
              disabled={ro}
              onChange={(e) => set('packing_status', e.target.value)}
            >
              {Object.entries(PACKING_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Вид транспорта">
            <select
              className="select"
              value={value('transport_mode') as string}
              disabled={ro}
              onChange={(e) => set('transport_mode', e.target.value)}
            >
              <option value="">—</option>
              {Object.entries(TRANSPORT_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          {num('freight_cost_plan', 'Фрахт — план')}
          {num('freight_cost_fact', 'Фрахт — факт')}
          {date('etd', 'ETD (отправка)')}
          {date('eta', 'ETA (прибытие)')}
          {date('eta_initial', 'ETA первоначальная')}
        </div>
        {deal.eta_slip_days !== null && deal.eta_slip_days > 0 && (
          <div className="error-box mt">
            ETA сдвинута на {deal.eta_slip_days} дн. относительно первоначальной.
          </div>
        )}
      </Panel>
      )}

      {isImport && (
      <Panel title="Блоки 14–18 · Брокер, ГТД, склад, приёмка">
        <div className="kv">
          {date('broker_docs_sent_at', 'Документы переданы брокеру')}
          {text('gtd_number', 'ГТД №')}
          {date('gtd_submitted_at', 'ГТД подана')}
          {date('gtd_released_at', 'ГТД выпущена')}
          {date('warehouse_notified_at', 'Склад уведомлён')}
          {date('actual_arrival', 'Фактическое прибытие')}
          {num('places_plan', 'Мест по документам')}
          {num('places_fact', 'Мест фактически')}
          <Field label="Упаковка при приёмке">
            <select
              className="select"
              value={value('packaging_ok') === '' ? '' : String(value('packaging_ok'))}
              disabled={ro}
              onChange={(e) => set('packaging_ok', e.target.value === '' ? null : e.target.value === 'true')}
            >
              <option value="">—</option>
              <option value="true">Норма</option>
              <option value="false">Повреждения</option>
            </select>
          </Field>
          <Field label="Маркировка соответствует">
            <select
              className="select"
              value={value('marking_ok') === '' ? '' : String(value('marking_ok'))}
              disabled={ro}
              onChange={(e) => set('marking_ok', e.target.value === '' ? null : e.target.value === 'true')}
            >
              <option value="">—</option>
              <option value="true">Да</option>
              <option value="false">Нет</option>
            </select>
          </Field>
          {text('act_number', 'Акт входного контроля №')}
          {date('act_date', 'Дата акта')}
        </div>
        {deal.places_plan !== null &&
          deal.places_fact !== null &&
          deal.places_plan !== deal.places_fact && (
            <div className="error-box mt">
              Расхождение по количеству мест: план {deal.places_plan}, факт {deal.places_fact} —
              требуется акт и претензия.
            </div>
          )}
      </Panel>
      )}

      {!isImport && (
        <Panel title="Доставка и приёмка">
          <div className="kv">
            <Field label="Вид транспорта">
              <select
                className="select"
                value={value('transport_mode') as string}
                disabled={ro}
                onChange={(e) => set('transport_mode', e.target.value)}
              >
                <option value="">—</option>
                {Object.entries(TRANSPORT_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>
            {num('freight_cost_plan', 'Стоимость — план')}
            {num('freight_cost_fact', 'Стоимость — факт')}
            {date('etd', 'Отправка (ETD)')}
            {date('eta', 'Прибытие (ETA)')}
            {date('warehouse_notified_at', 'Склад уведомлён')}
            {date('actual_arrival', 'Фактическое прибытие')}
            {num('places_plan', 'Мест по документам')}
            {num('places_fact', 'Мест фактически')}
            {text('act_number', 'Акт №')}
            {date('act_date', 'Дата акта')}
          </div>
        </Panel>
      )}

      <Comments dealId={deal.id} />
    </div>
  )
}

// ------------------------------------------------------------------ checklist
function Checklist({ dealId, currentStage }: { dealId: number; currentStage: number }) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const { data, reload } = useLiveData<ChecklistItem[]>(
    () => api.get(`/api/deals/${dealId}/checklist`),
    [dealId],
    (e) => e.startsWith('checklist') || e.startsWith('deal'),
  )

  async function toggle(item: ChecklistItem) {
    try {
      await api.patch(`/api/deals/${dealId}/checklist/${item.id}`, { is_done: !item.is_done })
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  if (!data) return <Loading />
  if (data.length === 0)
    return (
      <Panel title="Чек-лист">
        <Empty text="Для этого типа сделки чек-лист не задан — контроль идёт по маршруту этапов вверху карточки." />
      </Panel>
    )

  const sections = data.reduce<Record<string, ChecklistItem[]>>((acc, item) => {
    ;(acc[item.section] ??= []).push(item)
    return acc
  }, {})
  const done = data.filter((i) => i.is_done).length

  return (
    <Panel
      title={`Чек-лист ВЭД — ${done} из ${data.length}`}
      actions={
        <div style={{ width: 140 }}>
          <Progress pct={Math.round((done / Math.max(data.length, 1)) * 100)} label />
        </div>
      }
      tight
    >
      {Object.entries(sections).map(([section, items]) => (
        <div key={section}>
          <div className="check-section">{section}</div>
          {items.map((item) => (
            <label
              key={item.id}
              className={`check-row ${item.is_done ? 'done' : ''}`}
              style={
                item.stage_id === currentStage && !item.is_done
                  ? { background: 'var(--amber-soft)' }
                  : undefined
              }
            >
              <input
                type="checkbox"
                checked={item.is_done}
                disabled={!canEdit}
                onChange={() => toggle(item)}
              />
              <span className="code">{item.code}</span>
              <span className="title" style={{ flex: 1 }}>
                {item.title}
              </span>
              {item.stage_id === currentStage && !item.is_done && (
                <span className="badge amber">текущий этап</span>
              )}
              {item.done_at && <span className="small faint">{fmtDate(item.done_at)}</span>}
            </label>
          ))}
        </div>
      ))}
    </Panel>
  )
}

// ------------------------------------------------------------------ documents
function Documents({ dealId }: { dealId: number }) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const { data, reload } = useLiveData<DocumentItem[]>(
    () => api.get(`/api/deals/${dealId}/documents`),
    [dealId],
    (e) => e.startsWith('document') || e.startsWith('deal'),
  )

  async function patch(doc: DocumentItem, body: Record<string, any>) {
    try {
      await api.patch(`/api/deals/${dealId}/documents/${doc.id}`, body)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  async function upload(doc: DocumentItem, file: File) {
    try {
      await api.upload(`/api/deals/${dealId}/documents/${doc.id}/file`, file)
      notify(`Файл прикреплён к «${doc.name}»`)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось загрузить', 'err')
    }
  }

  function download(doc: DocumentItem) {
    fetch(apiUrl(`/api/deals/${dealId}/documents/${doc.id}/file`), {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error('Файл не найден'))))
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = doc.file_name || 'document'
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((e) => notify(e.message, 'err'))
  }

  if (!data) return <Loading />

  const required = data.filter((d) => d.is_required)
  const received = required.filter((d) => d.is_received).length
  const pct = required.length ? Math.round((received / required.length) * 100) : 0

  return (
    <Panel
      title={`Комплект документов — ${received} из ${required.length} обязательных`}
      actions={
        <div style={{ width: 140 }}>
          <Progress pct={pct} label />
        </div>
      }
      tight
    >
      <div className="table-wrap" style={{ border: 'none' }}>
        <table className="data" style={{ minWidth: 720 }}>
          <thead>
            <tr>
              <th style={{ width: 44 }}>✓</th>
              <th>Документ</th>
              <th>Номер</th>
              <th>Получен</th>
              <th>Файл</th>
            </tr>
          </thead>
          <tbody>
            {data.map((doc) => (
              <tr key={doc.id} style={{ cursor: 'default' }}>
                <td>
                  <input
                    type="checkbox"
                    checked={doc.is_received}
                    disabled={!canEdit}
                    style={{ width: 16, height: 16, accentColor: 'var(--green)' }}
                    onChange={() => patch(doc, { is_received: !doc.is_received })}
                  />
                </td>
                <td>
                  {doc.name}{' '}
                  {doc.is_required ? (
                    <span className="badge">обяз.</span>
                  ) : (
                    <span className="badge faint">опц.</span>
                  )}
                </td>
                <td>
                  <input
                    className="input"
                    style={{ minWidth: 130 }}
                    value={doc.number}
                    disabled={!canEdit}
                    onChange={(e) => patch(doc, { number: e.target.value })}
                  />
                </td>
                <td className="nowrap faint">{fmtDate(doc.received_at)}</td>
                <td className="nowrap">
                  {doc.file_name ? (
                    <div className="row" style={{ gap: 6 }}>
                      <button className="btn ghost sm" onClick={() => download(doc)}>
                        ↓ {doc.file_name.slice(0, 22)}
                      </button>
                      {canEdit && (
                        <button
                          className="btn ghost sm"
                          onClick={() =>
                            api
                              .del(`/api/deals/${dealId}/documents/${doc.id}/file`)
                              .then(reload)
                              .catch((e) => notify(e.message, 'err'))
                          }
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ) : canEdit ? (
                    <label className="btn ghost sm" style={{ cursor: 'pointer' }}>
                      + Файл
                      <input
                        type="file"
                        hidden
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) upload(doc, f)
                          e.target.value = ''
                        }}
                      />
                    </label>
                  ) : (
                    <span className="faint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

// ------------------------------------------------------------------ quotes
function Quotes({ dealId, onChanged }: { dealId: number; onChanged: () => void }) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [adding, setAdding] = useState(false)
  const { data, reload } = useLiveData<Quote[]>(
    () => api.get(`/api/deals/${dealId}/quotes`),
    [dealId],
    (e) => e.startsWith('quote') || e.startsWith('deal'),
  )

  const best = useMemo(() => {
    if (!data?.length) return null
    const priced = data.filter((q) => q.price !== null)
    if (!priced.length) return null
    return priced.reduce((a, b) => (Number(a.price) <= Number(b.price) ? a : b)).id
  }, [data])

  async function select(quote: Quote, reason: string) {
    try {
      await api.post(`/api/deals/${dealId}/quotes/${quote.id}/select`, { select_reason: reason })
      notify(`Выбран поставщик: ${quote.supplier?.name}`)
      reload()
      onChanged()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  if (!data) return <Loading />

  return (
    <>
      <Panel
        title={`Коммерческие предложения — ${data.length}`}
        actions={
          canEdit && (
            <button className="btn primary sm" onClick={() => setAdding(true)}>
              + КП
            </button>
          )
        }
        tight
      >
        {data.length === 0 ? (
          <Empty text="КП пока не внесены." />
        ) : (
          <div className="table-wrap" style={{ border: 'none' }}>
            <table className="data" style={{ minWidth: 820 }}>
              <thead>
                <tr>
                  <th>Поставщик</th>
                  <th className="num">Цена</th>
                  <th className="num">Срок, дн.</th>
                  <th>Условия оплаты</th>
                  <th>Инкотермс</th>
                  <th>Получено</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((q) => (
                  <tr
                    key={q.id}
                    style={{
                      cursor: 'default',
                      background: q.is_selected ? 'rgba(34,197,94,0.08)' : undefined,
                    }}
                  >
                    <td>
                      <b style={{ fontWeight: 550 }}>{q.supplier?.name}</b>
                      <div className="small faint">{q.supplier?.country}</div>
                    </td>
                    <td className="num nowrap">
                      {fmtMoney(q.price, q.currency)}
                      {best === q.id && <span className="badge green" style={{ marginLeft: 6 }}>мин.</span>}
                    </td>
                    <td className="num">{q.lead_time_days ?? '—'}</td>
                    <td>{q.payment_terms || '—'}</td>
                    <td>{q.incoterms || '—'}</td>
                    <td className="nowrap faint">{fmtDate(q.received_at)}</td>
                    <td className="nowrap">
                      {q.is_selected ? (
                        <span className="badge green">
                          Выбран{q.select_reason ? ` · ${REASON_LABELS[q.select_reason]}` : ''}
                        </span>
                      ) : (
                        canEdit && (
                          <select
                            className="select"
                            style={{ minWidth: 118 }}
                            value=""
                            onChange={(e) => e.target.value && select(q, e.target.value)}
                          >
                            <option value="">Выбрать…</option>
                            {Object.entries(REASON_LABELS).map(([k, v]) => (
                              <option key={k} value={k}>
                                по: {v}
                              </option>
                            ))}
                          </select>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {adding && (
        <AddQuote
          dealId={dealId}
          onClose={() => setAdding(false)}
          onAdded={() => {
            setAdding(false)
            reload()
          }}
        />
      )}
    </>
  )
}

function AddQuote({
  dealId,
  onClose,
  onAdded,
}: {
  dealId: number
  onClose: () => void
  onAdded: () => void
}) {
  const { notify } = useToast()
  const [form, setForm] = useState({
    supplier_id: '',
    price: '',
    currency: 'USD',
    lead_time_days: '',
    payment_terms: '',
    incoterms: '',
    received_at: '',
    note: '',
  })

  async function submit() {
    if (!form.supplier_id) return notify('Выберите поставщика', 'err')
    try {
      await api.post(`/api/deals/${dealId}/quotes`, {
        supplier_id: Number(form.supplier_id),
        price: form.price === '' ? null : form.price,
        currency: form.currency,
        lead_time_days: form.lead_time_days === '' ? null : Number(form.lead_time_days),
        payment_terms: form.payment_terms,
        incoterms: form.incoterms,
        received_at: form.received_at || null,
        note: form.note,
      })
      notify('КП добавлено')
      onAdded()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      title="Новое КП"
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={submit}>
            Добавить
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Поставщик">
          <SupplierPicker
            value={form.supplier_id === '' ? null : Number(form.supplier_id)}
            placeholder="— выберите —"
            onChange={(id) => set('supplier_id', id === null ? '' : String(id))}
          />
        </Field>
        <div className="grid-2">
          <Field label="Цена">
            <input
              className="input"
              type="number"
              value={form.price}
              onChange={(e) => set('price', e.target.value)}
            />
          </Field>
          <Field label="Валюта">
            <input className="input" value={form.currency} onChange={(e) => set('currency', e.target.value)} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Срок поставки, дней">
            <input
              className="input"
              type="number"
              value={form.lead_time_days}
              onChange={(e) => set('lead_time_days', e.target.value)}
            />
          </Field>
          <Field label="Инкотермс">
            <input
              className="input"
              value={form.incoterms}
              placeholder="FOB / CIF / EXW"
              onChange={(e) => set('incoterms', e.target.value)}
            />
          </Field>
        </div>
        <Field label="Условия оплаты">
          <input
            className="input"
            value={form.payment_terms}
            placeholder="30% предоплата / 70% против копий"
            onChange={(e) => set('payment_terms', e.target.value)}
          />
        </Field>
        <Field label="Дата получения">
          <input
            className="input"
            type="date"
            value={form.received_at}
            onChange={(e) => set('received_at', e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  )
}

// ------------------------------------------------------------------ claims
function Claims({ dealId }: { dealId: number }) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ kind: 'supplier', amount: '', currency: 'USD', description: '' })
  const { data, reload } = useLiveData<Claim[]>(
    () => api.get(`/api/deals/${dealId}/claims`),
    [dealId],
    (e) => e.startsWith('claim'),
  )

  async function add() {
    try {
      await api.post(`/api/deals/${dealId}/claims`, {
        kind: form.kind,
        amount: form.amount === '' ? null : form.amount,
        currency: form.currency,
        description: form.description,
        status: 'open',
      })
      notify('Претензия зарегистрирована')
      setAdding(false)
      setForm({ kind: 'supplier', amount: '', currency: 'USD', description: '' })
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  async function setStatus(claim: Claim, status: string) {
    try {
      await api.patch(`/api/deals/${dealId}/claims/${claim.id}`, {
        kind: claim.kind,
        amount: claim.amount,
        currency: claim.currency,
        description: claim.description,
        status,
      })
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  if (!data) return <Loading />

  return (
    <>
      <Panel
        title={`Претензии — ${data.length}`}
        actions={
          canEdit && (
            <button className="btn primary sm" onClick={() => setAdding(true)}>
              + Претензия
            </button>
          )
        }
      >
        {data.length === 0 ? (
          <Empty text="Претензий нет." />
        ) : (
          <div style={{ display: 'grid', gap: 11 }}>
            {data.map((c) => (
              <div
                key={c.id}
                style={{
                  padding: 12,
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-soft)',
                }}
              >
                <div className="row wrap">
                  <span className="badge">{c.kind === 'supplier' ? 'К поставщику' : 'К перевозчику'}</span>
                  <b>{fmtMoney(c.amount, c.currency)}</b>
                  <div style={{ flex: 1 }} />
                  {canEdit ? (
                    <select
                      className="select"
                      style={{ width: 168 }}
                      value={c.status}
                      onChange={(e) => setStatus(c, e.target.value)}
                    >
                      {Object.entries(CLAIM_STATUS_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="badge">{CLAIM_STATUS_LABELS[c.status]}</span>
                  )}
                </div>
                <div className="small mt">{c.description || '—'}</div>
                <div className="small faint" style={{ marginTop: 5 }}>
                  Создана {fmtDateTime(c.created_at)}
                  {c.resolved_at && ` · закрыта ${fmtDateTime(c.resolved_at)}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {adding && (
        <Modal
          title="Новая претензия"
          onClose={() => setAdding(false)}
          footer={
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setAdding(false)}>
                Отмена
              </button>
              <button className="btn primary" onClick={add}>
                Зарегистрировать
              </button>
            </div>
          }
        >
          <div style={{ display: 'grid', gap: 13 }}>
            <Field label="Кому">
              <select
                className="select"
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                <option value="supplier">Поставщику</option>
                <option value="carrier">Перевозчику</option>
              </select>
            </Field>
            <div className="grid-2">
              <Field label="Сумма">
                <input
                  className="input"
                  type="number"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                />
              </Field>
              <Field label="Валюта">
                <input
                  className="input"
                  value={form.currency}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                />
              </Field>
            </div>
            <Field label="Описание">
              <textarea
                className="textarea"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
          </div>
        </Modal>
      )}
    </>
  )
}

// ------------------------------------------------------------------ history & comments
function History({ dealId }: { dealId: number }) {
  const { data } = useLiveData<HistoryEvent[]>(
    () => api.get(`/api/deals/${dealId}/history`),
    [dealId],
    (e) => e.startsWith('deal'),
  )
  if (!data) return <Loading />
  return (
    <Panel title="История движения по этапам">
      {data.length === 0 ? (
        <Empty text="Событий нет." />
      ) : (
        <div className="timeline">
          {data.map((e) => (
            <div className="tl-item" key={e.id}>
              <div className="tl-dot" />
              <div>
                <div className="tl-body">
                  {e.from_stage_name ? (
                    <>
                      <span className="faint">{e.from_stage_name}</span> →{' '}
                      <b style={{ fontWeight: 570 }}>{e.to_stage_name}</b>
                    </>
                  ) : (
                    <b style={{ fontWeight: 570 }}>{e.to_stage_name}</b>
                  )}
                  {e.days_in_from_stage && (
                    <span className="badge" style={{ marginLeft: 8 }}>
                      {days(Number(e.days_in_from_stage))} на предыдущем
                    </span>
                  )}
                </div>
                {e.comment && <div className="small mt">{e.comment}</div>}
                <div className="tl-meta">
                  {fmtDateTime(e.created_at)} · {e.author}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function Comments({ dealId }: { dealId: number }) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [body, setBody] = useState('')
  const { data, reload } = useLiveData<Comment[]>(
    () => api.get(`/api/deals/${dealId}/comments`),
    [dealId],
    (e) => e.startsWith('comment'),
  )

  async function send() {
    if (!body.trim()) return
    try {
      await api.post(`/api/deals/${dealId}/comments`, { body: body.trim() })
      setBody('')
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  return (
    <Panel title={`Комментарии${data ? ` — ${data.length}` : ''}`}>
      {canEdit && (
        <div className="row" style={{ marginBottom: 14, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <textarea
              className="textarea"
              style={{ minHeight: 54 }}
              placeholder="Комментарий по сделке…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <button className="btn primary" onClick={send} disabled={!body.trim()}>
            Отправить
          </button>
        </div>
      )}
      {!data || data.length === 0 ? (
        <div className="small faint">Комментариев пока нет.</div>
      ) : (
        <div style={{ display: 'grid', gap: 11 }}>
          {data.map((c) => (
            <div key={c.id}>
              <div className="row" style={{ gap: 8 }}>
                <b style={{ fontSize: 12.5, fontWeight: 600 }}>{c.author}</b>
                <span className="small faint">{fmtDateTime(c.created_at)}</span>
              </div>
              <div className="small" style={{ marginTop: 2, whiteSpace: 'pre-wrap' }}>
                {c.body}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function MoveModal({
  stage,
  onClose,
  onConfirm,
}: {
  stage: Stage
  onClose: () => void
  onConfirm: (comment: string) => void
}) {
  const [comment, setComment] = useState('')
  return (
    <Modal
      title={`Перевести на этап ${stage.id}`}
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={() => onConfirm(comment)}>
            Перевести
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <div>
          <b style={{ fontSize: 15 }}>{stage.name}</b>
          <p className="small muted" style={{ marginTop: 5 }}>
            {stage.description}
          </p>
          <div className="row wrap small faint" style={{ gap: 14, marginTop: 8 }}>
            <span>Ответственный: {stage.responsible}</span>
            <span>Периодичность: {stage.frequency}</span>
            {stage.sla_days !== null && <span>Норматив: {stage.sla_days} дн.</span>}
          </div>
        </div>
        <Field label="Комментарий (необязательно)">
          <textarea
            className="textarea"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Что сделано на предыдущем этапе…"
          />
        </Field>
      </div>
    </Modal>
  )
}
