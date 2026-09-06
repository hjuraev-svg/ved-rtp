import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useLiveData, useToast } from '../store'
import type { Dashboard as DashboardData, Pipeline, Tile } from '../types'
import { Empty, ErrorBox, Loading } from '../components/ui'
import { GripIcon, StageIcon } from '../components/icons'
import { GROUP_COLORS, days, fmtDateTime } from '../util'

interface Layout {
  tile_order: number[]
  hidden: number[]
  is_custom: boolean
}

const PIPE_KEY = 'ved_pipeline'

export default function Dashboard({ navigate }: { navigate: (p: string) => void }) {
  const { notify } = useToast()
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  // Remembered per browser so the dashboard opens on the type you work with.
  const [pipeline, setPipeline] = useState(() => localStorage.getItem(PIPE_KEY) || 'import')

  useEffect(() => {
    api.get<Pipeline[]>('/api/pipelines').then(setPipelines).catch(() => undefined)
  }, [])
  useEffect(() => {
    localStorage.setItem(PIPE_KEY, pipeline)
  }, [pipeline])

  const { data, error, loading } = useLiveData<DashboardData>(
    () => api.get<DashboardData>(`/api/dashboard?pipeline=${pipeline}`),
    [pipeline],
  )

  const [order, setOrder] = useState<number[]>([])
  const [hidden, setHidden] = useState<number[]>([])
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const dragId = useRef<number | null>(null)
  const [overId, setOverId] = useState<number | null>(null)
  // Snapshot taken when edit mode opens, so Отмена can restore it.
  const snapshot = useRef<{ order: number[]; hidden: number[] } | null>(null)

  useEffect(() => {
    api
      .get<Layout>('/api/dashboard/layout')
      .then((l) => {
        setOrder(l.tile_order)
        setHidden(l.hidden)
      })
      .catch(() => undefined)
  }, [])

  const tiles = data?.tiles ?? []

  const ordered = useMemo(() => {
    if (!tiles.length) return []
    const byId = new Map(tiles.map((t) => [t.stage_id, t]))
    const out: Tile[] = []
    for (const id of order) {
      const t = byId.get(id)
      if (t) {
        out.push(t)
        byId.delete(id)
      }
    }
    // Anything not in the saved order (e.g. a newly added block) goes last.
    for (const t of tiles) if (byId.has(t.stage_id)) out.push(t)
    return out
  }, [tiles, order])

  const visible = editing ? ordered : ordered.filter((t) => !hidden.includes(t.stage_id))

  function move(from: number, to: number) {
    if (from === to) return
    setOrder((prev) => {
      const base = prev.length ? [...prev] : ordered.map((t) => t.stage_id)
      const i = base.indexOf(from)
      const j = base.indexOf(to)
      if (i < 0 || j < 0) return base
      base.splice(j, 0, base.splice(i, 1)[0])
      return base
    })
  }

  function openEdit() {
    const current = order.length ? order : ordered.map((t) => t.stage_id)
    snapshot.current = { order: current, hidden: [...hidden] }
    setOrder(current)
    setEditing(true)
  }

  function cancelEdit() {
    if (snapshot.current) {
      setOrder(snapshot.current.order)
      setHidden(snapshot.current.hidden)
    }
    setEditing(false)
  }

  async function save() {
    setBusy(true)
    try {
      const saved = await api.put<Layout>('/api/dashboard/layout', {
        tile_order: order.length ? order : ordered.map((t) => t.stage_id),
        hidden,
      })
      setOrder(saved.tile_order)
      setHidden(saved.hidden)
      setEditing(false)
      notify('Расположение сохранено')
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось сохранить', 'err')
    } finally {
      setBusy(false)
    }
  }

  async function reset() {
    setBusy(true)
    try {
      const l = await api.del<Layout>('/api/dashboard/layout')
      setOrder(l.tile_order)
      setHidden(l.hidden)
      setEditing(false)
      notify('Восстановлен порядок по процессу')
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось сбросить', 'err')
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  const { alerts, groups } = data

  return (
    <>
      {pipelines.length > 1 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="tabs">
            {pipelines.map((p) => (
              <button
                key={p.code}
                className={`tab ${pipeline === p.code ? 'active' : ''}`}
                title={p.description}
                onClick={() => setPipeline(p.code)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {editing ? (
        <div className="editbar">
          <b style={{ fontSize: 13 }}>Настройка дашборда</b>
          <span className="hint-text">
            Перетащите плитку на новое место · нажмите «глаз», чтобы скрыть
          </span>
          <div style={{ flex: 1 }} />
          <button className="btn sm" onClick={reset} disabled={busy}>
            ↺ Сбросить
          </button>
          <button className="btn sm" onClick={cancelEdit} disabled={busy}>
            Отмена
          </button>
          <button className="btn primary sm" onClick={save} disabled={busy}>
            {busy ? 'Сохранение…' : '✓ Готово'}
          </button>
        </div>
      ) : (
        <div className="row wrap" style={{ marginBottom: 12 }}>
          <div className="legend">
            {groups.map((g) => (
              <span key={g.key}>
                <i className="dot" style={{ background: g.color }} />
                {g.name}
              </span>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          {hidden.length > 0 && (
            <span className="badge">скрыто плиток: {hidden.length}</span>
          )}
          <button className="btn sm" onClick={openEdit}>
            ⠿ Настроить
          </button>
        </div>
      )}

      <div className={`tiles ${editing ? 'editing' : ''}`}>
        {visible.map((tile) => {
          const isHidden = hidden.includes(tile.stage_id)
          return (
            <button
              key={tile.stage_id}
              className={`tile ${editing && dragId.current === tile.stage_id ? 'dragging' : ''} ${
                overId === tile.stage_id ? 'drop-target' : ''
              } ${isHidden ? 'hidden-tile' : ''}`}
              style={
                { '--accent': GROUP_COLORS[tile.group_key] ?? '#3b82f6' } as React.CSSProperties
              }
              title={editing ? 'Перетащите на новое место' : `${tile.group_name} · открыть список`}
              draggable={editing}
              onDragStart={(e) => {
                dragId.current = tile.stage_id
                e.dataTransfer.effectAllowed = 'move'
                // Firefox refuses to start a drag without data set.
                e.dataTransfer.setData('text/plain', String(tile.stage_id))
              }}
              onDragOver={(e) => {
                if (!editing || dragId.current === null) return
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                if (overId !== tile.stage_id) setOverId(tile.stage_id)
              }}
              onDrop={(e) => {
                if (!editing || dragId.current === null) return
                e.preventDefault()
                move(dragId.current, tile.stage_id)
                dragId.current = null
                setOverId(null)
              }}
              onDragEnd={() => {
                dragId.current = null
                setOverId(null)
              }}
              onClick={() => {
                if (!editing) navigate(`deals?stage=${tile.stage_id}`)
              }}
            >
              <span className="tile-no">{tile.stage_id}</span>
              {tile.overdue > 0 && !editing && <span className="tile-flag">{tile.overdue}</span>}

              <span className="tile-icon">
                <StageIcon code={tile.code} />
              </span>
              <span
                className={`tile-count ${
                  tile.overdue > 0 ? 'danger' : tile.count === 0 ? 'zero' : ''
                }`}
              >
                {tile.count}
              </span>
              <span className="tile-name">{tile.name}</span>
              <span className="tile-sub">
                {tile.count === 0
                  ? 'нет сделок'
                  : tile.overdue > 0
                    ? `${tile.overdue} в красной зоне`
                    : tile.sla_days !== null
                      ? `ср. ${tile.avg_days_in_stage} из ${tile.sla_days} дн.`
                      : `ср. ${tile.avg_days_in_stage} дн. в пути`}
              </span>

              {editing && (
                <>
                  <span className="tile-grip">
                    <GripIcon />
                  </span>
                  <span
                    className="tile-eye"
                    role="button"
                    tabIndex={-1}
                    title={isHidden ? 'Показать плитку' : 'Скрыть плитку'}
                    onClick={(e) => {
                      e.stopPropagation()
                      setHidden((h) =>
                        h.includes(tile.stage_id)
                          ? h.filter((x) => x !== tile.stage_id)
                          : [...h, tile.stage_id],
                      )
                    }}
                  >
                    {isHidden ? '🚫' : '👁'}
                  </span>
                </>
              )}
            </button>
          )
        })}
      </div>

      <div className="section-title">
        Требуют внимания {alerts.length > 0 && `· ${alerts.length}`}
      </div>
      <div className="card">
        {alerts.length === 0 ? (
          <Empty text="Просрочек нет — все сделки в пределах нормативов." />
        ) : (
          alerts.map((a, i) => (
            <div
              className="alert-row"
              key={`${a.deal_id}-${a.kind}-${i}`}
              onClick={() => navigate(`deal/${a.deal_id}`)}
            >
              <span className="badge red" style={{ marginTop: 1 }}>
                {a.kind === 'sla'
                  ? 'Простой'
                  : a.kind === 'eta_slip'
                    ? 'ETA сдвиг'
                    : a.kind === 'eta_overdue'
                      ? 'ETA прошла'
                      : a.kind === 'production_slip'
                        ? 'Производство'
                        : a.kind === 'customs_slow'
                          ? 'Таможня'
                          : a.kind === 'unk_missing'
                            ? 'УНК'
                            : 'Внимание'}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="row wrap" style={{ gap: 8 }}>
                  <span className="mono faint">{a.code}</span>
                  <b style={{ fontWeight: 570 }}>{a.title}</b>
                </div>
                <div className="small faint" style={{ marginTop: 2 }}>
                  {a.stage_name} · {a.detail}
                </div>
              </div>
              <span className="badge nowrap">{days(a.days_in_stage)}</span>
            </div>
          ))
        )}
      </div>

      <div className="small faint" style={{ marginTop: 14, textAlign: 'right' }}>
        Обновлено: {fmtDateTime(data.generated_at)} · данные обновляются автоматически
      </div>
    </>
  )
}
