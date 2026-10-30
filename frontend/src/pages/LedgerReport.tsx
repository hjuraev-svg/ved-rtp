import { api } from '../api'
import { useLiveData } from '../store'
import type { LedgerReport as Report } from '../types'
import { Empty } from '../components/ui'
import { fmtMoney } from '../util'

/** Отчёт дебет / кредит по финансовому реестру — блок дашборда.
 *  Кредит — выставлено поставщиками, дебет — оплачено нами, сальдо — наш долг.
 *  Валюты не складываются: курса на дату у строки реестра нет. */
export default function LedgerReport({ navigate }: { navigate: (p: string) => void }) {
  const { data } = useLiveData<Report>(
    () => api.get('/api/ledger/report'),
    [],
    (e) => e.startsWith('ledger') || e.startsWith('supplier'),
  )

  return (
    <>
      <div className="section-title row">
        Дебет / кредит по поставщикам
        <div style={{ flex: 1 }} />
        <button className="btn ghost sm" onClick={() => navigate('ledger')}>
          Финансовый процесс →
        </button>
      </div>

      {!data ? null : data.totals.length === 0 ? (
        <div className="card">
          <Empty text="В финансовом процессе пока нет записей — внесите инвойсы поставщиков, и здесь появится отчёт." />
        </div>
      ) : (
        <>
          {data.totals.map((t) => (
            <div className="kpi-row" key={t.currency} style={{ marginBottom: 10 }}>
              <div className="card kpi">
                <div className="label">Кредит · {t.currency}</div>
                <div className="value" style={{ fontSize: 19 }}>{fmtMoney(t.credit, t.currency)}</div>
                <div className="sub">выставлено инвойсов: {t.records}</div>
              </div>
              <div className="card kpi">
                <div className="label">Дебет · {t.currency}</div>
                <div className="value" style={{ fontSize: 19 }}>{fmtMoney(t.debit, t.currency)}</div>
                <div className="sub">оплачено поставщикам</div>
              </div>
              <div className="card kpi">
                <div className="label">Сальдо (долг) · {t.currency}</div>
                <div className="value" style={{ fontSize: 19 }}>{fmtMoney(t.balance, t.currency)}</div>
                <div className="sub">кредит − дебет</div>
              </div>
              <div className="card kpi">
                <div className="label">Просрочено · {t.currency}</div>
                <div
                  className="value"
                  style={{ fontSize: 19, color: Number(t.overdue) > 0 ? 'var(--red)' : undefined }}
                >
                  {fmtMoney(t.overdue, t.currency)}
                </div>
                <div className="sub">записей с прошедшим сроком: {t.overdue_records}</div>
              </div>
            </div>
          ))}

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Поставщик</th>
                  <th>Кредит (инвойсы)</th>
                  <th>Дебет (оплачено)</th>
                  <th>Сальдо (долг)</th>
                  <th>Из них просрочено</th>
                </tr>
              </thead>
              <tbody>
                {data.suppliers.map((s) => (
                  <tr key={`${s.supplier_id}-${s.currency}`} onClick={() => navigate('ledger')}>
                    <td>
                      <b style={{ fontWeight: 550 }}>{s.supplier}</b>
                      <span className="small faint"> · записей {s.records}</span>
                    </td>
                    <td className="nowrap num">{fmtMoney(s.credit, s.currency)}</td>
                    <td className="nowrap num">{fmtMoney(s.debit, s.currency)}</td>
                    <td className="nowrap num">
                      <b style={{ fontWeight: 600 }}>{fmtMoney(s.balance, s.currency)}</b>
                    </td>
                    <td className="nowrap">
                      {Number(s.overdue) > 0 ? (
                        <span className="badge red">{fmtMoney(s.overdue, s.currency)}</span>
                      ) : (
                        <span className="faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
