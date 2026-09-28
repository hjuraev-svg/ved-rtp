import { useState } from 'react'
import { api } from '../api'
import { useLiveData } from '../store'
import type { Finance as FinanceData, Money, Pipeline } from '../types'
import { Empty, ErrorBox, Loading, Panel } from '../components/ui'
import { fmtDate, fmtMoney } from '../util'

/** Суммы не приводятся к одной валюте: курс на дату есть не у каждого платежа,
 *  а складывать доллары с юанями без него — выдумывать цифру. */
function money(list: Money[]) {
  return list.length ? list.map((m) => fmtMoney(m.amount, m.currency)).join(' · ') : '—'
}

export default function Finance({ navigate }: { navigate: (path: string) => void }) {
  const [pipeline, setPipeline] = useState('')
  const { data: pipelines } = useLiveData<Pipeline[]>(() => api.get('/api/pipelines'), [])
  const { data, loading, error } = useLiveData<FinanceData>(
    () => api.get(`/api/dashboard/finance${pipeline ? `?pipeline=${pipeline}` : ''}`),
    [pipeline],
    (e) => e.startsWith('payment') || e.startsWith('item') || e.startsWith('deal'),
  )

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  return (
    <>
      <div className="filters">
        <select className="select" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
          <option value="">Все типы сделок</option>
          {(pipelines ?? []).map((p) => (
            <option key={p.code} value={p.code}>{p.name}</option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        {data.overdue_count > 0 && (
          <span className="badge red">Просроченных платежей: {data.overdue_count}</span>
        )}
      </div>

      <div className="kpi-row">
        <div className="card kpi">
          <div className="label">Законтрактовано</div>
          <div className="value" style={{ fontSize: 19 }}>{money(data.contracted)}</div>
          <div className="sub">по действующим сделкам</div>
        </div>
        <div className="card kpi">
          <div className="label">Оплачено</div>
          <div className="value" style={{ fontSize: 19 }}>{money(data.paid_out)}</div>
          <div className="sub">исходящие платежи</div>
        </div>
        <div className={`card kpi ${data.debt_count ? 'alert' : ''}`}>
          <div className="label">К оплате</div>
          <div className="value" style={{ fontSize: 19 }}>{money(data.planned_out)}</div>
          <div className="sub">сделок с остатком: {data.debt_count}</div>
        </div>
        <div className="card kpi">
          <div className="label">Выручка получена</div>
          <div className="value" style={{ fontSize: 19 }}>{money(data.paid_in)}</div>
          <div className="sub">ожидается: {money(data.planned_in)}</div>
        </div>
      </div>

      <Panel title="График платежей">
        {!data.schedule.length ? (
          <Empty text="Плановых платежей нет. Заведите их во вкладке «Платежи» в карточке сделки." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Срок</th>
                  <th>Сделка</th>
                  <th>Поставщик</th>
                  <th>Вид</th>
                  <th className="num">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {data.schedule.map((s) => (
                  <tr key={s.payment_id} onClick={() => navigate(`deal/${s.deal_id}`)}>
                    <td className="nowrap">
                      <span className={s.overdue ? 'badge red' : ''}>{fmtDate(s.due_date) || 'без срока'}</span>
                    </td>
                    <td>
                      <div className="mono small faint">{s.code}</div>
                      <div>{s.title}</div>
                    </td>
                    <td className="nowrap">{s.supplier}</td>
                    <td className="nowrap small">
                      {s.direction === 'in' ? 'Поступление' : 'Оплата'}
                    </td>
                    <td className="num nowrap"><b>{fmtMoney(s.amount, s.currency)}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div style={{ height: 16 }} />

      <Panel title={`Задолженность по сделкам${data.debt_count > data.debts.length ? ` · показано ${data.debts.length} из ${data.debt_count}` : ''}`}>
        {!data.debts.length ? (
          <Empty text="Непогашенных остатков нет." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Сделка</th>
                  <th>Поставщик</th>
                  <th className="num">Контракт</th>
                  <th className="num">Оплачено</th>
                  <th className="num">Остаток</th>
                </tr>
              </thead>
              <tbody>
                {data.debts.map((d) => (
                  <tr key={d.deal_id} onClick={() => navigate(`deal/${d.deal_id}`)}>
                    <td>
                      <div className="mono small faint">{d.code}</div>
                      <div>{d.title}</div>
                    </td>
                    <td className="nowrap">{d.supplier}</td>
                    <td className="num nowrap">{fmtMoney(d.contract_amount, d.currency)}</td>
                    <td className="num nowrap faint">{fmtMoney(d.paid, d.currency)}</td>
                    <td className="num nowrap">
                      <b style={{ color: 'var(--red)' }}>{fmtMoney(d.rest, d.currency)}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  )
}
