import { useMemo, useState } from 'react'
import { api } from '../api'
import { useLiveData } from '../store'
import { Empty, Loading, Panel } from '../components/ui'

interface RatingRow {
  supplier_id: number
  supplier: string
  country: string
  category: string
  deals: number
  avg_cycle_days: number | null
  on_time_pct: number | null
  judged_deliveries: number
  avg_slip_days: number | null
  claims: number
  thin: boolean
}

export default function SupplierRating() {
  const [category, setCategory] = useState('')
  const { data } = useLiveData<RatingRow[]>(
    () => api.get('/api/dashboard/supplier-rating'),
    [],
    (e) => e.startsWith('deal') || e.startsWith('supplier'),
  )

  const categories = useMemo(
    () => [...new Set((data ?? []).map((r) => r.category).filter(Boolean))].sort(),
    [data],
  )
  const shown = useMemo(
    () => (category ? (data ?? []).filter((r) => r.category === category) : data ?? []),
    [data, category],
  )
  // Сколько поставщиков вообще поддаются оценке по срокам
  const measurable = useMemo(
    () => (data ?? []).filter((r) => r.on_time_pct !== null).length,
    [data],
  )

  if (!data) return <Loading />

  return (
    <>
      <div className="filters">
        <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Все категории</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <span className="small faint nowrap">поставщиков: {shown.length}</span>
      </div>

      {measurable === 0 && data.length > 0 && (
        <div className="card" style={{ marginBottom: 16, borderColor: 'var(--amber, #f59e0b)' }}>
          <div className="small">
            <b>Сроки пока не считаются.</b> Соблюдение сроков и длительность цикла берутся из
            ETA и фактической даты прибытия — в архивных сделках их нет. Колонки заполнятся, когда
            эти даты начнут вноситься в карточках.
          </div>
        </div>
      )}

      <Panel title="Рейтинг по исполненным поставкам">
        {shown.length === 0 ? (
          <Empty text="Закрытых сделок ещё нет." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Поставщик</th>
                  <th>Категория</th>
                  <th>Страна</th>
                  <th className="num">Поставок</th>
                  <th className="num">Цикл, дн</th>
                  <th className="num">В срок</th>
                  <th className="num">Сдвиг, дн</th>
                  <th className="num">Претензий</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.supplier_id}>
                    <td>
                      <b style={{ fontWeight: 550 }}>{r.supplier}</b>
                      {r.thin && (
                        <span className="badge" style={{ marginLeft: 6 }} title="Мало поставок для выводов">
                          мало данных
                        </span>
                      )}
                    </td>
                    <td className="small">{r.category || '—'}</td>
                    <td className="small faint">{r.country || '—'}</td>
                    <td className="num"><b>{r.deals}</b></td>
                    <td className="num faint">{r.avg_cycle_days ?? '—'}</td>
                    <td className="num">
                      {r.on_time_pct === null ? (
                        <span className="faint">—</span>
                      ) : (
                        <span className={`badge ${r.on_time_pct >= 90 ? 'green' : r.on_time_pct >= 70 ? 'amber' : 'red'}`}>
                          {r.on_time_pct}%
                        </span>
                      )}
                    </td>
                    <td className="num faint">{r.avg_slip_days ?? '—'}</td>
                    <td className="num">
                      {r.claims > 0 ? <span className="badge red">{r.claims}</span> : <span className="faint">0</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="small faint" style={{ marginTop: 10 }}>
          Считается только по закрытым сделкам: у незавершённой нет итога, и включать её значит
          хвалить поставщика авансом. «В срок» — прибытие не позже ETA, по тем поставкам, где обе
          даты заполнены.
        </div>
      </Panel>
    </>
  )
}
