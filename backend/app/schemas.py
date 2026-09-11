import re
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A login is either a plain username ("Saamandar") or an email
# ("aziz@company.uz"). Strict RFC validators are wrong here twice over: they
# reject bare usernames, and they reject special-use domains like `.local`.
# Stored and compared lower-cased, so logins are case-insensitive.
_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._@+-]*[A-Za-z0-9])?$")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    # Column is named `email` for historical reasons; it holds the login.
    email: str = Field(min_length=3, max_length=160)
    full_name: str
    role: str = "ved"
    password: str = Field(min_length=4)

    @field_validator("email")
    @classmethod
    def check_login(cls, v: str) -> str:
        v = v.strip().lower()
        if not _LOGIN_RE.match(v):
            raise ValueError(
                "Логин: латинские буквы, цифры и . _ - + @ — без пробелов"
            )
        return v


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=160)
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)

    @field_validator("email")
    @classmethod
    def check_login(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not _LOGIN_RE.match(v):
            raise ValueError("Логин: латинские буквы, цифры и . _ - + @ — без пробелов")
        return v


# ---------- stages ----------
class StageOut(ORMModel):
    id: int
    pipeline: str
    code: str
    name: str
    group_name: str
    group_key: str
    description: str
    how_to_count: str
    data_source: str
    frequency: str
    responsible: str
    sla_days: int | None


class StageUpdate(BaseModel):
    sla_days: int | None = None
    responsible: str | None = None
    frequency: str | None = None


# ---------- suppliers ----------
class SupplierOut(ORMModel):
    id: int
    name: str
    country: str
    category: str
    contact_person: str
    email: str
    phone: str
    messenger: str
    telegram_chat_id: str
    notes: str
    is_active: bool


class SupplierIn(BaseModel):
    name: str
    country: str = ""
    category: str = ""
    contact_person: str = ""
    email: str = ""
    phone: str = ""
    messenger: str = ""
    telegram_chat_id: str = ""
    notes: str = ""
    is_active: bool = True


# ---------- deals ----------
class DealBase(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    requester: str = ""
    assignee_id: int | None = None
    supplier_id: int | None = None
    country: str = ""
    incoterms: str = ""
    contract_number: str = ""
    contract_date: date | None = None
    contract_amount: Decimal | None = None
    currency: str = "USD"
    unk_number: str = ""
    unk_date: date | None = None
    payment_confirmed_at: date | None = None
    payment_amount: Decimal | None = None
    order_confirmation_at: date | None = None
    production_ready_plan: date | None = None
    production_ready_fact: date | None = None
    packing_status: str = "not_started"
    transport_mode: str = ""
    freight_cost_plan: Decimal | None = None
    freight_cost_fact: Decimal | None = None
    etd: date | None = None
    eta: date | None = None
    eta_initial: date | None = None
    broker_docs_sent_at: date | None = None
    gtd_number: str = ""
    gtd_submitted_at: date | None = None
    gtd_released_at: date | None = None
    warehouse_notified_at: date | None = None
    actual_arrival: date | None = None
    places_plan: int | None = None
    places_fact: int | None = None
    packaging_ok: bool | None = None
    marking_ok: bool | None = None
    act_number: str = ""
    act_date: date | None = None


class DealCreate(DealBase):
    pipeline: str = "import"
    stage_id: int | None = None  # defaults to the pipeline's first stage


class DealUpdate(BaseModel):
    """All-optional patch. `stage_id` is intentionally absent — use /move."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    requester: str | None = None
    assignee_id: int | None = None
    supplier_id: int | None = None
    country: str | None = None
    incoterms: str | None = None
    contract_number: str | None = None
    contract_date: date | None = None
    contract_amount: Decimal | None = None
    currency: str | None = None
    unk_number: str | None = None
    unk_date: date | None = None
    payment_confirmed_at: date | None = None
    payment_amount: Decimal | None = None
    order_confirmation_at: date | None = None
    production_ready_plan: date | None = None
    production_ready_fact: date | None = None
    packing_status: str | None = None
    transport_mode: str | None = None
    freight_cost_plan: Decimal | None = None
    freight_cost_fact: Decimal | None = None
    etd: date | None = None
    eta: date | None = None
    eta_initial: date | None = None
    broker_docs_sent_at: date | None = None
    gtd_number: str | None = None
    gtd_submitted_at: date | None = None
    gtd_released_at: date | None = None
    warehouse_notified_at: date | None = None
    actual_arrival: date | None = None
    places_plan: int | None = None
    places_fact: int | None = None
    packaging_ok: bool | None = None
    marking_ok: bool | None = None
    act_number: str | None = None
    act_date: date | None = None


class DealMove(BaseModel):
    stage_id: int = Field(ge=1)
    comment: str = ""


class DealPipelineChange(BaseModel):
    pipeline: str


class MiniSupplier(ORMModel):
    id: int
    name: str
    country: str


class MiniUser(ORMModel):
    id: int
    full_name: str
    role: str


class DealOut(DealBase, ORMModel):
    id: int
    code: str
    status: str
    pipeline: str
    stage_id: int
    stage_name: str = ""
    stage_group: str = ""
    stage_group_key: str = ""
    supplier: MiniSupplier | None = None
    assignee: MiniUser | None = None
    stage_entered_at: datetime
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    # computed
    days_in_stage: float = 0
    sla_days: int | None = None
    is_overdue: bool = False
    eta_slip_days: int | None = None
    docs_ready_pct: int = 0
    checklist_done_pct: int = 0


class DealListOut(BaseModel):
    items: list[DealOut]
    total: int
    page: int
    page_size: int


# ---------- checklist / docs / quotes / claims / comments ----------
class ChecklistOut(ORMModel):
    id: int
    template_id: int
    code: str = ""
    title: str = ""
    section: str = ""
    stage_id: int = 0
    is_done: bool
    done_at: datetime | None
    done_by_id: int | None
    note: str


class ChecklistPatch(BaseModel):
    is_done: bool | None = None
    note: str | None = None


class DocumentOut(ORMModel):
    id: int
    doc_type_id: int
    code: str = ""
    name: str = ""
    is_required: bool = True
    is_received: bool
    received_at: date | None
    number: str
    file_name: str
    note: str


class DocumentPatch(BaseModel):
    is_received: bool | None = None
    received_at: date | None = None
    number: str | None = None
    note: str | None = None


class QuoteIn(BaseModel):
    supplier_id: int
    price: Decimal | None = None
    currency: str = "USD"
    lead_time_days: int | None = None
    payment_terms: str = ""
    incoterms: str = ""
    received_at: date | None = None
    note: str = ""


class QuoteOut(ORMModel):
    id: int
    deal_id: int
    supplier_id: int
    supplier: MiniSupplier | None = None
    price: Decimal | None
    currency: str
    lead_time_days: int | None
    payment_terms: str
    incoterms: str
    is_selected: bool
    select_reason: str
    received_at: date | None
    note: str


class QuoteSelect(BaseModel):
    select_reason: str = "price"  # price | lead_time | quality | recommendation


class ClaimIn(BaseModel):
    kind: str = "supplier"
    amount: Decimal | None = None
    currency: str = "USD"
    description: str = ""
    status: str = "open"


class ClaimOut(ORMModel):
    id: int
    deal_id: int
    kind: str
    amount: Decimal | None
    currency: str
    description: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class CommentIn(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(ORMModel):
    id: int
    deal_id: int
    user_id: int | None
    author: str = ""
    body: str
    created_at: datetime


# ---------- Gmail / Telegram communications ----------
class IntegrationOut(BaseModel):
    provider: str
    status: str
    configured: bool
    label: str = ""
    last_synced_at: datetime | None = None
    last_error: str = ""


class CommunicationSend(BaseModel):
    provider: str
    body: str = Field(min_length=1, max_length=20000)
    subject: str = Field(default="", max_length=500)
    recipient: str = Field(default="", max_length=320)


class CommunicationMessageOut(ORMModel):
    id: int
    deal_id: int | None
    provider: str
    direction: str
    external_id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    status: str
    sent_at: datetime | None
    received_at: datetime | None
    created_at: datetime


class EventOut(ORMModel):
    id: int
    deal_id: int
    from_stage_id: int | None
    to_stage_id: int
    from_stage_name: str = ""
    to_stage_name: str = ""
    days_in_from_stage: Decimal | None
    comment: str
    user_id: int | None
    author: str = ""
    created_at: datetime


# ---------- dashboard ----------
class TileOut(BaseModel):
    stage_id: int
    pipeline: str = "import"
    code: str
    name: str
    group_key: str
    group_name: str
    count: int
    overdue: int
    sla_days: int | None
    entered_this_week: int
    avg_days_in_stage: float


class AlertOut(BaseModel):
    deal_id: int
    code: str
    title: str
    stage_id: int
    stage_name: str
    days_in_stage: float
    sla_days: int | None
    kind: str  # sla | eta_slip | production_slip | docs_incomplete
    detail: str


class MoneyOut(BaseModel):
    currency: str
    amount: Decimal


class KpiOut(BaseModel):
    active_deals: int
    overdue_deals: int
    contracts_signed_month: int
    contracts_amount_month: list[MoneyOut]
    in_transit: int
    arriving_this_week: int
    avg_customs_days: float | None
    docs_ready_pct: int
    open_claims: int
    claims_amount: list[MoneyOut]
    unk_registered: int
    unk_missing: int


class LayoutIn(BaseModel):
    tile_order: list[int] = Field(default_factory=list)
    hidden: list[int] = Field(default_factory=list)


class LayoutOut(BaseModel):
    tile_order: list[int]
    hidden: list[int]
    is_custom: bool


class DashboardOut(BaseModel):
    generated_at: datetime
    pipeline: str
    tiles: list[TileOut]
    kpi: KpiOut
    alerts: list[AlertOut]
    groups: list[dict]


TokenOut.model_rebuild()
