export const GROUP_COLORS: Record<string, string> = {
  // Импорт (ВЭД)
  purchase: '#3b82f6',
  contract: '#8b5cf6',
  production: '#f59e0b',
  customs: '#06b6d4',
  receiving: '#22c55e',
  // Местный поставщик
  local_deal: '#8b5cf6',
  local_production: '#f59e0b',
  local_receiving: '#22c55e',
  // Услуга
  svc_pickup: '#3b82f6',
  svc_terms: '#f59e0b',
  svc_done: '#22c55e',
}

export const PIPELINE_LABELS: Record<string, string> = {
  import: 'Импорт (ВЭД)',
  local: 'Местный поставщик',
  service: 'Услуга',
}

export const STATUS_LABELS: Record<string, string> = {
  active: 'В работе',
  on_hold: 'На паузе',
  done: 'Завершена',
  cancelled: 'Отменена',
}

export const PRIORITY_LABELS: Record<string, string> = {
  low: 'Низкий',
  normal: 'Обычный',
  high: 'Высокий',
  critical: 'Критичный',
}

export const TRANSPORT_LABELS: Record<string, string> = {
  sea: 'Море',
  road: 'Авто',
  rail: 'ЖД',
  air: 'Авиа',
}

export const PACKING_LABELS: Record<string, string> = {
  not_started: 'Не начато',
  requirements_sent: 'Требования отправлены',
  confirmed: 'Подтверждено поставщиком',
}

export const REASON_LABELS: Record<string, string> = {
  price: 'Цена',
  lead_time: 'Срок',
  quality: 'Качество',
  recommendation: 'Рекомендация',
}

export const CLAIM_STATUS_LABELS: Record<string, string> = {
  open: 'Открыта',
  in_progress: 'В работе',
  settled: 'Урегулирована',
  rejected: 'Отклонена',
}

export const ROLE_LABELS: Record<string, string> = {
  admin: 'Администратор',
  ved: 'Специалист ВЭД',
  director: 'Директор',
  logist: 'Логист',
  warehouse: 'Склад',
  accountant: 'Бухгалтерия',
  broker: 'Брокер',
  viewer: 'Наблюдатель',
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value.length <= 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtMoney(value: string | number | null | undefined, currency = ''): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return '—'
  const s = n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
  return currency ? `${s} ${currency}` : s
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export function days(n: number): string {
  const r = Math.round(n)
  return `${r} ${plural(r, 'день', 'дня', 'дней')}`
}

/** Convert an ISO datetime/date to the value an <input type="date"> expects. */
export function dateInput(value: string | null | undefined): string {
  if (!value) return ''
  return value.slice(0, 10)
}

export function progressClass(pct: number): string {
  if (pct >= 80) return 'progress'
  if (pct >= 50) return 'progress mid'
  return 'progress low'
}
