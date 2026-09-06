import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Pipeline, Stage } from '../types'
import { Loading, Panel } from '../components/ui'
import { GROUP_COLORS } from '../util'

export default function Blocks() {
  const { user } = useAuth()
  const { notify } = useToast()
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [pipeline, setPipeline] = useState('import')

  useEffect(() => {
    api.get<Pipeline[]>('/api/pipelines').then(setPipelines).catch(() => undefined)
  }, [])

  const { data, reload } = useLiveData<Stage[]>(
    () => api.get(`/api/stages?pipeline=${pipeline}`),
    [pipeline],
  )
  const [editing, setEditing] = useState<number | null>(null)
  const [sla, setSla] = useState('')

  const canEditSla = user?.role === 'admin' || user?.role === 'director'

  async function saveSla(stage: Stage) {
    try {
      await api.patch(`/api/stages/${stage.id}`, {
        sla_days: sla === '' ? null : Number(sla),
      })
      notify(`Норматив блока «${stage.name}» обновлён`)
      setEditing(null)
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Ошибка', 'err')
    }
  }

  if (!data) return <Loading />

  const groups = data.reduce<Record<string, Stage[]>>((acc, s) => {
    ;(acc[s.group_key] ??= []).push(s)
    return acc
  }, {})

  return (
    <>
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

      <p className="muted" style={{ marginTop: 0, maxWidth: 780 }}>
        Справочник построен из листа «Описание блоков» исходного файла. «Норматив» — это красная
        зона: сколько дней сделка может находиться на этапе, прежде чем попадёт в раздел «Требуют
        внимания».
      </p>

      {Object.entries(groups).map(([key, stages]) => (
        <div key={key} style={{ marginBottom: 18 }}>
          <div className="tile-group-head">
            <i className="dot" style={{ background: GROUP_COLORS[key] }} />
            <h3>{stages[0].group_name}</h3>
          </div>
          <div className="table-wrap">
            <table className="data" style={{ minWidth: 1050 }}>
              <thead>
                <tr>
                  <th style={{ width: 38 }}>№</th>
                  <th style={{ width: 190 }}>Блок</th>
                  <th>Что показывает</th>
                  <th>Как считается / что вносить</th>
                  <th style={{ width: 170 }}>Источник данных</th>
                  <th style={{ width: 130 }}>Периодичность</th>
                  <th style={{ width: 160 }}>Ответственный</th>
                  <th style={{ width: 110 }}>Норматив</th>
                </tr>
              </thead>
              <tbody>
                {stages.map((s) => (
                  <tr key={s.id} style={{ cursor: 'default' }}>
                    <td className="faint num">{s.id}</td>
                    <td>
                      <b style={{ fontWeight: 570 }}>{s.name}</b>
                    </td>
                    <td className="muted">{s.description}</td>
                    <td className="muted small">{s.how_to_count}</td>
                    <td className="small faint">{s.data_source}</td>
                    <td className="small faint">{s.frequency}</td>
                    <td className="small faint">{s.responsible}</td>
                    <td>
                      {editing === s.id ? (
                        <div className="row" style={{ gap: 5 }}>
                          <input
                            className="input"
                            type="number"
                            style={{ width: 62 }}
                            value={sla}
                            autoFocus
                            onChange={(e) => setSla(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && saveSla(s)}
                          />
                          <button className="btn primary sm" onClick={() => saveSla(s)}>
                            ✓
                          </button>
                        </div>
                      ) : (
                        <span
                          className="badge"
                          style={{ cursor: canEditSla ? 'pointer' : 'default' }}
                          onClick={() => {
                            if (!canEditSla) return
                            setEditing(s.id)
                            setSla(s.sla_days === null ? '' : String(s.sla_days))
                          }}
                        >
                          {s.sla_days === null ? 'по ETA' : `${s.sla_days} дн.`}
                          {canEditSla && ' ✎'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {pipeline === 'import' && (
        <Panel title="Чек-лист ВЭД (шаблон)">
          <ChecklistTemplate />
        </Panel>
      )}
    </>
  )
}

function ChecklistTemplate() {
  const { data } = useLiveData<{ id: number; code: string; title: string; section: string; stage_id: number }[]>(
    () => api.get('/api/checklist-template?pipeline=import'),
    [],
  )
  if (!data) return <Loading />

  const sections = data.reduce<Record<string, typeof data>>((acc, item) => {
    ;(acc[item.section] ??= []).push(item)
    return acc
  }, {})

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      {Object.entries(sections).map(([section, items]) => (
        <div key={section}>
          <div className="section-title" style={{ margin: '0 0 6px' }}>
            {section}
          </div>
          {items.map((i) => (
            <div className="row small" key={i.id} style={{ padding: '3px 0' }}>
              <span className="faint mono" style={{ minWidth: 30 }}>
                {i.code}
              </span>
              <span>{i.title}</span>
              <span className="badge" style={{ marginLeft: 'auto' }}>
                блок {i.stage_id}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
