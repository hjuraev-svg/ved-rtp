import { useState } from 'react'
import { api } from '../api'
import { useLiveData } from '../store'
import { Empty, ErrorBox, Loading, Panel } from '../components/ui'
import { fmtMoney } from '../util'

interface FunnelDeal {
  deal_id: number
  code: string
  title: string
  supplier: string
  currency: string
  contract_amount: string | null
  paid: string
  rest: string | null
  missing_docs: string[]
  unk_missing: boolean
}

interface FunnelStage {
  key: string
  name: string
  hint: string
  color: string
  count: number
  amounts: { currency: string; amount: string }[]
  deals: FunnelDeal[]
}

interface FunnelData {
  pipeline: string | null
  total_deals: number
  stages: FunnelStage[]
  by_supplier: { supplier: string; currency: string; rest: string }[]
}

const DOC_LABELS: Record<string, string> = {
  contract: 'контракт',
  invoice: 'инвойс',
  local_contract: 'договор',
  local_invoice: 'счёт',
  svc_invoice: 'счёт за услугу',
  exp_contract: 'экспортный контракт',
  exp_invoice: 'инвойс',
}

export default function FinanceFunnel({
  pipeline,
  navigate,
}: {
  pipeline: string
  navigate: (path: string) => void
}) {
  const [open, setOpen] = useState<string | null>(null)

  const { data, loading, error } = useLiveData<FunnelData>(
    () => api.get(`/api/dashboard/finance-funnel${pipeline ? `?pipeline=${pipeline}` : ''}`),
    [pipeline],
    (e) => e.startsWith('payment') || e.startsWith('deal') || e.startsWith('item') || e.startsWith('doc'),
  )

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  const money = (list: { currency: string; amount: string }[]) =>
    list.length ? list.map((m) => fmtMoney(m.amount, m.currency)).join(' · ') : '—'

  const shown = data.stages.find((s) => s.key === open)

  return (
    <>
      {/* Этапы взаимоисключающие, поэтому сумма плиток равна числу сделок —
          по такой воронке можно принимать решение, а не только смотреть. */}
      <div className="kpi-row">
        {data.stages.map((s) => (
          <div
            key={s.key}
            className="card kpi"
            style={{
              cursor: 'pointer',
              borderLeft: `3px solid ${s.color}`,
              outline: open === s.key ? `1px solid ${s.color}` : undefined,
            }}
            onClick={() => setOpen(open === s.key ? null : s.key)}
          >
            <div className="label">{s.name}</div>
            <div className="value" style={{ color: s.count ? s.color : undefined }}>{s.count}</div>
            <div className="sub">{money(s.amounts)}</div>
            <div className="sub faint" style={{ fontSize: 11 }}>{s.hint}</div>
          </div>
        ))}
      </div>

      {shown && (
        <Panel title={`${shown.name} · ${shown.count}`}>
          {shown.deals.length === 0 ? (
            <Empty text="Здесь пусто." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Сделка</th>
                    <th>Поставщик</th>
                    <th className="num">Сумма</th>
                    <th className="num">Оплачено</th>
                    <th className="num">Остаток</th>
                    <th>Чего не хватает</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.deals.map((d) => (
                    <tr key={d.deal_id} onClick={() => navigate(`deal/${d.deal_id}`)}>
                      <td>
                        <div className="mono small faint">{d.code}</div>
                        <div>{d.title}</div>
                      </td>
                      <td className="nowrap">{d.supplier}</td>
                      <td className="num nowrap">
                        {d.contract_amount ? fmtMoney(d.contract_amount, d.currency) : <span className="faint">не заведена</span>}
                      </td>
                      <td className="num nowrap faint">{fmtMoney(d.paid, d.currency)}</td>
                      <td className="num nowrap">
                        {d.rest !== null && Number(d.rest) > 0
                          ? <b style={{ color: 'var(--red)' }}>{fmtMoney(d.rest, d.currency)}</b>
                          : <span className="faint">—</span>}
                      </td>
                      <td className="small">
                        {d.missing_docs.map((c) => (
                          <span key={c} className="badge amber" style={{ marginRight: 4 }}>
                            {DOC_LABELS[c] ?? c}
                          </span>
                        ))}
                        {d.unk_missing && <span className="badge red">УНК</span>}
                        {!d.missing_docs.length && !d.unk_missing && <span className="faint">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      <div style={{ height: 16 }} />

      <Panel title="Кому сколько должны">
        {data.by_supplier.length === 0 ? (
          <Empty text="Непогашенных остатков нет." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Поставщик</th><th className="num">Остаток</th></tr>
              </thead>
              <tbody>
                {data.by_supplier.map((r, i) => (
                  <tr key={i}>
                    <td>{r.supplier}</td>
                    <td className="num nowrap">
                      <b style={{ color: 'var(--red)' }}>{fmtMoney(r.rest, r.currency)}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="small faint" style={{ marginTop: 8 }}>
          {data.pipeline ? 'По выбранному типу сделок' : 'По всем типам: импорт, местные закупки, услуги и экспорт'}
          {' — '}сделок в работе: {data.total_deals}. Сделка попадает ровно в один этап, поэтому
          сумма плиток равна этому числу. Валюты не сводятся к одной: курса на дату в системе нет,
          а складывать их без него — выдумывать цифру.
        </div>
      </Panel>
    </>
  )
}
