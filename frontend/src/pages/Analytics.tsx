import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLiveData } from '../store'
import type { CycleTime, Pipeline } from '../types'
import { Empty, Loading, Panel } from '../components/ui'
import { GROUP_COLORS, fmtMoney } from '../util'

interface SupplierRow {
  supplier: string
  country: string
  currency: string
  deals: number
  amount: number
}

export default function Analytics() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [pipeline, setPipeline] = useState(
    () => localStorage.getItem('ved_pipeline') || 'import',
  )

  useEffect(() => {
    api.get<Pipeline[]>('/api/pipelines').then(setPipelines).catch(() => undefined)
  }, [])

  const { data: cycles } = useLiveData<CycleTime[]>(
    () => api.get(`/api/dashboard/cycle-times?pipeline=${pipeline}`),
    [pipeline],
  )
  const { data: bySupplier } = useLiveData<SupplierRow[]>(
    () => api.get('/api/dashboard/by-supplier'),
    [],
  )
  const { data: throughput } = useLiveData<{ week: string; count: number }[]>(
    () => api.get(`/api/dashboard/throughput?pipeline=${pipeline}`),
    [pipeline],
  )

  if (!cycles) return <Loading />

  const maxDays = Math.max(1, ...cycles.map((c) => Math.max(c.avg_days, c.sla_days ?? 0)))

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {pipelines.length > 1 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="tabs">
            {pipelines.map((p) => (
              <button
                key={p.code}
                className={`tab ${pipeline === p.code ? 'active' : ''}`}
                onClick={() => setPipeline(p.code)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <Panel title="Среднее время на этапе (за 90 дней) против норматива">
        <div className="bars">
          {cycles.map((c) => {
            const over = c.sla_days !== null && c.avg_days > c.sla_days
            return (
              <div className="bar-row" key={c.stage_id}>
                <span className="small" title={c.name}>
                  <span className="faint">{c.stage_id}.</span> {c.name}
                </span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${(c.avg_days / maxDays) * 100}%`,
                      background: over ? 'var(--red)' : (GROUP_COLORS[c.group_key] ?? 'var(--blue)'),
                    }}
                  />
                  {c.sla_days !== null && (
                    <div className="bar-sla" style={{ left: `${(c.sla_days / maxDays) * 100}%` }} />
                  )}
                </div>
                <span className={`small num ${over ? 'badge red' : 'faint'}`}>
                  {c.avg_days} дн.
                </span>
              </div>
            )
          })}
        </div>
        <div className="small faint mt">
          Красная вертикальная линия — норматив блока. Учитываются только завершённые переходы
          ({cycles.reduce((s, c) => s + c.samples, 0)} шт.).
        </div>
      </Panel>

      <Panel title="Завершено сделок по неделям">
        {!throughput || throughput.length === 0 ? (
          <Empty text="Пока нет завершённых сделок за период." />
        ) : (
          <Sparkline data={throughput} />
        )}
      </Panel>

      <Panel title="Контракты по поставщикам и странам">
        {!bySupplier || bySupplier.length === 0 ? (
          <Empty text="Нет контрактов с указанной суммой." />
        ) : (
          <div className="table-wrap" style={{ border: 'none' }}>
            <table className="data" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th>Поставщик</th>
                  <th>Страна</th>
                  <th className="num">Сделок</th>
                  <th className="num">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {bySupplier.map((r, i) => (
                  <tr key={i} style={{ cursor: 'default' }}>
                    <td>{r.supplier}</td>
                    <td className="faint">{r.country}</td>
                    <td className="num">{r.deals}</td>
                    <td className="num nowrap">{fmtMoney(r.amount, r.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}

function Sparkline({ data }: { data: { week: string; count: number }[] }) {
  const w = 720
  const h = 150
  const pad = 26
  const max = Math.max(1, ...data.map((d) => d.count))
  const step = data.length > 1 ? (w - pad * 2) / (data.length - 1) : 0

  const points = data.map((d, i) => ({
    x: pad + i * step,
    y: h - pad - (d.count / max) * (h - pad * 2),
    ...d,
  }))
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: 'auto', overflow: 'visible' }}>
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--border)" />
      <path d={path} fill="none" stroke="var(--blue)" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3.5} fill="var(--blue)" />
          <text x={p.x} y={p.y - 9} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
            {p.count}
          </text>
          {(i === 0 || i === points.length - 1 || i % 3 === 0) && (
            <text
              x={p.x}
              y={h - pad + 15}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-faint)"
            >
              {new Date(p.week).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
            </text>
          )}
        </g>
      ))}
    </svg>
  )
}
