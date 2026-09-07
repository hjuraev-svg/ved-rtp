export interface User {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}

export interface Pipeline {
  code: string
  name: string
  short: string
  prefix: string
  description: string
}

export interface Stage {
  id: number
  pipeline: string
  code: string
  name: string
  group_name: string
  group_key: string
  description: string
  how_to_count: string
  data_source: string
  frequency: string
  responsible: string
  sla_days: number | null
}

export interface Supplier {
  id: number
  name: string
  country: string
  contact_person: string
  email: string
  phone: string
  messenger: string
  telegram_chat_id: string
  notes: string
  is_active: boolean
}

export interface Deal {
  id: number
  code: string
  title: string
  description: string
  pipeline: string
  stage_id: number
  stage_name: string
  stage_group: string
  stage_group_key: string
  status: string
  priority: string
  requester: string
  assignee_id: number | null
  supplier_id: number | null
  supplier: { id: number; name: string; country: string } | null
  assignee: { id: number; full_name: string; role: string } | null
  country: string
  incoterms: string
  contract_number: string
  contract_date: string | null
  contract_amount: string | null
  currency: string
  unk_number: string
  unk_date: string | null
  payment_confirmed_at: string | null
  payment_amount: string | null
  order_confirmation_at: string | null
  production_ready_plan: string | null
  production_ready_fact: string | null
  packing_status: string
  transport_mode: string
  freight_cost_plan: string | null
  freight_cost_fact: string | null
  etd: string | null
  eta: string | null
  eta_initial: string | null
  broker_docs_sent_at: string | null
  gtd_number: string
  gtd_submitted_at: string | null
  gtd_released_at: string | null
  warehouse_notified_at: string | null
  actual_arrival: string | null
  places_plan: number | null
  places_fact: number | null
  packaging_ok: boolean | null
  marking_ok: boolean | null
  act_number: string
  act_date: string | null
  stage_entered_at: string
  created_at: string
  updated_at: string
  closed_at: string | null
  days_in_stage: number
  sla_days: number | null
  is_overdue: boolean
  eta_slip_days: number | null
  docs_ready_pct: number
  checklist_done_pct: number
}

export interface Tile {
  stage_id: number
  pipeline: string
  code: string
  name: string
  group_key: string
  group_name: string
  count: number
  overdue: number
  sla_days: number | null
  entered_this_week: number
  avg_days_in_stage: number
}

export interface Alert {
  deal_id: number
  code: string
  title: string
  stage_id: number
  stage_name: string
  days_in_stage: number
  sla_days: number | null
  kind: string
  detail: string
}

export interface Money {
  currency: string
  amount: string
}

export interface Kpi {
  active_deals: number
  overdue_deals: number
  contracts_signed_month: number
  contracts_amount_month: Money[]
  in_transit: number
  arriving_this_week: number
  avg_customs_days: number | null
  docs_ready_pct: number
  open_claims: number
  claims_amount: Money[]
  unk_registered: number
  unk_missing: number
}

export interface Dashboard {
  generated_at: string
  pipeline: string
  tiles: Tile[]
  kpi: Kpi
  alerts: Alert[]
  groups: { key: string; name: string; color: string }[]
}

export interface ChecklistItem {
  id: number
  template_id: number
  code: string
  title: string
  section: string
  stage_id: number
  is_done: boolean
  done_at: string | null
  done_by_id: number | null
  note: string
}

export interface DocumentItem {
  id: number
  doc_type_id: number
  code: string
  name: string
  is_required: boolean
  is_received: boolean
  received_at: string | null
  number: string
  file_name: string
  note: string
}

export interface Quote {
  id: number
  deal_id: number
  supplier_id: number
  supplier: { id: number; name: string; country: string } | null
  price: string | null
  currency: string
  lead_time_days: number | null
  payment_terms: string
  incoterms: string
  is_selected: boolean
  select_reason: string
  received_at: string | null
  note: string
}

export interface Claim {
  id: number
  deal_id: number
  kind: string
  amount: string | null
  currency: string
  description: string
  status: string
  created_at: string
  resolved_at: string | null
}

export interface Comment {
  id: number
  deal_id: number
  user_id: number | null
  author: string
  body: string
  created_at: string
}

export interface HistoryEvent {
  id: number
  deal_id: number
  from_stage_id: number | null
  to_stage_id: number
  from_stage_name: string
  to_stage_name: string
  days_in_from_stage: string | null
  comment: string
  author: string
  created_at: string
}

export interface CycleTime {
  stage_id: number
  name: string
  group_key: string
  avg_days: number
  sla_days: number | null
  samples: number
}

export interface Integration {
  provider: string
  status: string
  configured: boolean
  label: string
  last_synced_at: string | null
  last_error: string
}

export interface CommunicationMessage {
  id: number
  deal_id: number | null
  provider: string
  direction: string
  external_id: string
  sender: string
  recipients: string[]
  subject: string
  body: string
  status: string
  sent_at: string | null
  received_at: string | null
  created_at: string
}
