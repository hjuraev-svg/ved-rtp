import { useEffect, useState } from 'react'
import { api, apiUrl, getToken } from '../api'
import { useAuth, useLiveData, useToast } from '../store'
import type { Deal, Pipeline, Stage } from '../types'
import { Empty, ErrorBox, Field, Loading, Modal, Progress } from '../components/ui'
import SupplierPicker from '../components/SupplierPicker'
import { PIPELINE_LABELS, PRIORITY_LABELS, days, fmtDate, fmtMoney } from '../util'

interface Props {
  navigate: (path: string) => void
  initialStage: number | null
  initialPipeline: string | null
}

export default function Deals({ navigate, initialStage, initialPipeline }: Props) {
  const { canEdit } = useAuth()
  const { notify } = useToast()

  const [pipeline, setPipeline] = useState<string>(initialPipeline ?? '')
  const [stageId, setStageId] = useState<number | null>(initialStage)
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [status, setStatus] = useState('active')
  const [priority, setPriority] = useState('')
  const [overdueOnly, setOverdueOnly] = useState(false)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('oldest_in_stage')
  const [creating, setCreating] = useState(false)

  useEffect(() => setStageId(initialStage), [initialStage])
  useEffect(() => {
    if (initialPipeline) setPipeline(initialPipeline)
  }, [initialPipeline])
  useEffect(() => {
    api.get<Pipeline[]>('/api/pipelines').then(setPipelines).catch(() => undefined)
  }, [])

  // Stage list follows the selected type, so the two filters can never disagree.
  const { data: stages } = useLiveData<Stage[]>(
    () => api.get(pipeline ? `/api/stages?pipeline=${pipeline}` : '/api/stages'),
    [pipeline],
    (e) => e.startsWith('stage'),
  )

  const params = new URLSearchParams()
  if (pipeline) params.set('pipeline', pipeline)
  if (stageId) params.set('stage_id', String(stageId))
  if (status) params.set('status', status)
  if (priority) params.set('priority', priority)
  if (overdueOnly) params.set('overdue_only', 'true')
  if (q.trim()) params.set('q', q.trim())
  params.set('sort', sort)
  params.set('page_size', '200')
  const query = params.toString()

  const { data, error, loading, reload } = useLiveData<{ items: Deal[]; total: number }>(
    () => api.get(`/api/deals?${query}`),
    [query],
  )

  function exportCsv() {
    // The download endpoint needs the bearer token, so fetch as a blob.
    fetch(apiUrl('/api/export/deals.csv'), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => {
        if (!r.ok) throw new Error('Не удалось выгрузить')
        return r.blob()
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'ved_deals.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((e) => notify(e.message, 'err'))
  }

  return (
    <>
      <div className="filters">
        <input
          className="input grow"
          placeholder="Поиск: наименование, код, контракт, ГТД, УНК…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="select"
          value={pipeline}
          onChange={(e) => {
            setPipeline(e.target.value)
            setStageId(null) // stages differ per type
          }}
        >
          <option value="">Все типы</option>
          {pipelines.map((p) => (
            <option key={p.code} value={p.code}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={stageId ?? ''}
          onChange={(e) => setStageId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Все этапы</option>
          {stages?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id}. {s.name}
            </option>
          ))}
        </select>
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">В работе</option>
          <option value="on_hold">На паузе</option>
          <option value="done">Завершённые</option>
          <option value="cancelled">Отменённые</option>
        </select>
        <select className="select" value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">Любой приоритет</option>
          {Object.entries(PRIORITY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="oldest_in_stage">Дольше всех на этапе</option>
          <option value="updated_desc">Недавно изменённые</option>
          <option value="stage_asc">По этапу ↑</option>
          <option value="stage_desc">По этапу ↓</option>
          <option value="code_asc">По коду</option>
        </select>
        <button
          className={`btn ${overdueOnly ? 'primary' : ''}`}
          onClick={() => setOverdueOnly((v) => !v)}
        >
          🔴 Красная зона
        </button>
        <button className="btn" onClick={exportCsv}>
          ↓ CSV
        </button>
        {canEdit && (
          <button className="btn primary" onClick={() => setCreating(true)}>
            + Сделка
          </button>
        )}
      </div>

      {error && <ErrorBox message={error} />}
      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <div className="card">
          <Empty text="Сделок по заданным фильтрам нет." />
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Код</th>
                  <th>Наименование</th>
                  <th>Тип</th>
                  <th>Этап</th>
                  <th>Поставщик</th>
                  <th className="num">Сумма</th>
                  <th className="num">На этапе</th>
                  <th>Док.</th>
                  <th>Чек-лист</th>
                  <th>ETA</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.id} onClick={() => navigate(`deal/${d.id}`)}>
                    <td className="mono faint nowrap">{d.code}</td>
                    <td>
                      <div style={{ fontWeight: 550 }}>{d.title}</div>
                      {d.priority !== 'normal' && (
                        <span className={`badge ${d.priority === 'critical' || d.priority === 'high' ? 'amber' : ''}`}>
                          {PRIORITY_LABELS[d.priority]}
                        </span>
                      )}
                    </td>
                    <td className="nowrap small faint">
                      {PIPELINE_LABELS[d.pipeline] ?? d.pipeline}
                    </td>
                    <td className="nowrap">
                      <span className="badge">{d.stage_name}</span>
                    </td>
                    <td className="nowrap">{d.supplier?.name ?? '—'}</td>
                    <td className="num nowrap">{fmtMoney(d.contract_amount, d.currency)}</td>
                    <td className="num nowrap">
                      <span className={d.is_overdue ? 'badge red' : ''}>
                        {days(d.days_in_stage)}
                      </span>
                    </td>
                    <td style={{ minWidth: 84 }}>
                      <Progress pct={d.docs_ready_pct} label />
                    </td>
                    <td style={{ minWidth: 84 }}>
                      <Progress pct={d.checklist_done_pct} label />
                    </td>
                    <td className="nowrap faint">{fmtDate(d.eta)}</td>
                    <td className="faint">›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="small faint" style={{ marginTop: 10 }}>
            Показано {data.items.length} из {data.total}
          </div>
        </>
      )}

      {creating && (
        <CreateDeal
          pipelines={pipelines}
          defaultPipeline={pipeline || 'import'}
          onClose={() => setCreating(false)}
          onCreated={(deal) => {
            setCreating(false)
            reload()
            navigate(`deal/${deal.id}`)
          }}
        />
      )}
    </>
  )
}

function CreateDeal({
  pipelines,
  defaultPipeline,
  onClose,
  onCreated,
}: {
  pipelines: Pipeline[]
  defaultPipeline: string
  onClose: () => void
  onCreated: (deal: Deal) => void
}) {
  const { notify } = useToast()
  const [pipeline, setPipeline] = useState(defaultPipeline)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [requester, setRequester] = useState('')
  const [priority, setPriority] = useState('normal')
  const [stageId, setStageId] = useState<number | null>(null)
  const [supplierId, setSupplierId] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [stages, setStages] = useState<Stage[]>([])

  // Choosing the type reloads its stages and resets the starting stage,
  // so a deal can never be created on a stage from another type.
  useEffect(() => {
    setStageId(null)
    api
      .get<Stage[]>(`/api/stages?pipeline=${pipeline}`)
      .then((st) => {
        setStages(st)
        setStageId(st.length ? st[0].id : null)
      })
      .catch(() => setStages([]))
  }, [pipeline])

  const current = pipelines.find((p) => p.code === pipeline)

  async function submit() {
    if (!title.trim()) return notify('Укажите наименование', 'err')
    setBusy(true)
    try {
      const deal = await api.post<Deal>('/api/deals', {
        title: title.trim(),
        description,
        requester,
        priority,
        pipeline,
        stage_id: stageId,
        supplier_id: supplierId ? Number(supplierId) : null,
      })
      notify(`Создана сделка ${deal.code}`)
      onCreated(deal)
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось создать', 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Новая сделка"
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? 'Создание…' : 'Создать'}
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Тип сделки">
          <select
            className="select"
            value={pipeline}
            onChange={(e) => setPipeline(e.target.value)}
          >
            {pipelines.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
          </select>
          {current && <div className="small faint" style={{ marginTop: 5 }}>{current.description}</div>}
        </Field>
        <Field label="Наименование">
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: Стеклофлаконы 100 мл — 40 000 шт"
            autoFocus
          />
        </Field>
        <div className="grid-2">
          <Field label="Заявитель">
            <input
              className="input"
              value={requester}
              onChange={(e) => setRequester(e.target.value)}
              placeholder="Директор производства"
            />
          </Field>
          <Field label="Приоритет">
            <select className="select" value={priority} onChange={(e) => setPriority(e.target.value)}>
              {Object.entries(PRIORITY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Начальный этап">
            <select
              className="select"
              value={stageId ?? ''}
              onChange={(e) => setStageId(Number(e.target.value))}
            >
              {stages.map((s, i) => (
                <option key={s.id} value={s.id}>
                  {i + 1}. {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Поставщик (если известен)">
            <SupplierPicker
              value={supplierId === '' ? null : Number(supplierId)}
              onChange={(id) => setSupplierId(id === null ? '' : String(id))}
            />
          </Field>
        </div>
        <Field label="Описание">
          <textarea
            className="textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <div className="small faint">
          {pipeline === 'import'
            ? 'Чек-лист (24 пункта) и комплект документов создаются автоматически.'
            : 'Комплект документов для этого типа создаётся автоматически.'}
          {' '}Этапов в маршруте: {stages.length}.
        </div>
      </div>
    </Modal>
  )
}
