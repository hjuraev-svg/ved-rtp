from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    # admin | ved | director | logist | warehouse | accountant | broker | viewer
    role: Mapped[str] = mapped_column(String(32), default="ved")
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Stage(Base):
    """The 18 dashboard blocks, seeded from «Описание блоков»."""

    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Which deal type this stage belongs to: import | local | service
    pipeline: Mapped[str] = mapped_column(String(16), default="import", index=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    group_name: Mapped[str] = mapped_column(String(80))
    group_key: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, default="")
    how_to_count: Mapped[str] = mapped_column(Text, default="")
    data_source: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[str] = mapped_column(String(80), default="")
    responsible: Mapped[str] = mapped_column(String(120), default="")
    # «Красная зона» — days a deal may sit in this stage before it turns red.
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    # Товарная категория: Парфюмерия, Оборудование, Ингредиенты, Транспорт…
    # Свободный текст, а не перечисление: номенклатура закупок меняется чаще,
    # чем стоило бы править схему.
    category: Mapped[str] = mapped_column(String(80), default="", index=True)
    contact_person: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    # WhatsApp / WeChat / Telegram / GMAIL — per block 2 data source
    messenger: Mapped[str] = mapped_column(String(160), default="")
    telegram_chat_id: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deal(Base):
    """One tracked ВЭД case: заявка → контракт → отгрузка → приёмка."""

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")

    # Deal type — decides which stages, documents and checklist apply.
    pipeline: Mapped[str] = mapped_column(String(16), default="import", index=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), index=True, default=1)
    # active | on_hold | done | cancelled
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # low | normal | high | critical
    priority: Mapped[str] = mapped_column(String(16), default="normal")

    requester: Mapped[str] = mapped_column(String(160), default="")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)

    country: Mapped[str] = mapped_column(String(80), default="")
    incoterms: Mapped[str] = mapped_column(String(16), default="")

    # --- Блок 5-6: контракт ---
    contract_number: Mapped[str] = mapped_column(String(80), default="")
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")

    # --- Блок 7: валютный контроль (УНК) ---
    unk_number: Mapped[str] = mapped_column(String(80), default="")
    unk_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Блок 8: подтверждение поступления денег ---
    payment_confirmed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    order_confirmation_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Блок 9: производство (план/факт) ---
    production_ready_plan: Mapped[date | None] = mapped_column(Date, nullable=True)
    production_ready_fact: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Блок 10: упаковка / маркировка ---
    # not_started | requirements_sent | confirmed
    packing_status: Mapped[str] = mapped_column(String(32), default="not_started")

    # --- Блок 11: фрахт ---
    transport_mode: Mapped[str] = mapped_column(String(16), default="")  # sea|road|rail|air
    freight_cost_plan: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    freight_cost_fact: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)

    # --- Блок 12: в пути ---
    etd: Mapped[date | None] = mapped_column(Date, nullable=True)
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    eta_initial: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Блок 14-15: брокер и ГТД ---
    broker_docs_sent_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    gtd_number: Mapped[str] = mapped_column(String(80), default="")
    gtd_submitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    gtd_released_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Блок 16-17: склад и входной контроль ---
    warehouse_notified_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_arrival: Mapped[date | None] = mapped_column(Date, nullable=True)
    places_plan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    places_fact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packaging_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marking_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Блок 18: акт ---
    act_number: Mapped[str] = mapped_column(String(80), default="")
    act_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stage: Mapped[Stage] = relationship(lazy="joined")
    supplier: Mapped[Supplier | None] = relationship(lazy="joined")
    assignee: Mapped[User | None] = relationship(lazy="joined")


class StageEvent(Base):
    """Audit trail of stage transitions — feeds cycle-time metrics."""

    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    from_stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id"), nullable=True)
    to_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    days_in_from_stage: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ChecklistTemplate(Base):
    """The 24 rows of «Чеклист ВЭД»."""

    __tablename__ = "checklist_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # "1.1", "7.7"
    pipeline: Mapped[str] = mapped_column(String(16), default="import", index=True)
    title: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(120), default="")
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    order_no: Mapped[int] = mapped_column(Integer, default=0)


class DealChecklist(Base):
    __tablename__ = "deal_checklist"
    __table_args__ = (UniqueConstraint("deal_id", "template_id", name="uq_deal_checklist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id"))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    template: Mapped[ChecklistTemplate] = relationship(lazy="joined")


class DocType(Base):
    """Document set behind block 13 «Отгрузочные документы»."""

    __tablename__ = "doc_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    pipeline: Mapped[str] = mapped_column(String(16), default="import", index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    order_no: Mapped[int] = mapped_column(Integer, default=0)


class DealDocument(Base):
    __tablename__ = "deal_documents"
    __table_args__ = (UniqueConstraint("deal_id", "doc_type_id", name="uq_deal_document"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    doc_type_id: Mapped[int] = mapped_column(ForeignKey("doc_types.id"))
    is_received: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    number: Mapped[str] = mapped_column(String(120), default="")
    file_name: Mapped[str] = mapped_column(String(300), default="")
    file_path: Mapped[str] = mapped_column(String(400), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    doc_type: Mapped[DocType] = relationship(lazy="joined")


class Quote(Base):
    """КП from a supplier — block 3, compared on price / lead time / terms."""

    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    price: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_terms: Mapped[str] = mapped_column(String(200), default="")
    incoterms: Mapped[str] = mapped_column(String(16), default="")
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    # price | lead_time | quality | recommendation
    select_reason: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    supplier: Mapped[Supplier] = relationship(lazy="joined")


class Claim(Base):
    """Претензия — block 18."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="supplier")  # supplier | carrier
    amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    description: Mapped[str] = mapped_column(Text, default="")
    # open | in_progress | settled | rejected
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserDashboard(Base):
    """Per-account tile arrangement. Absent row = default process order."""

    __tablename__ = "user_dashboard"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tile_order: Mapped[list] = mapped_column(JSON, default=list)
    hidden: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationConnection(Base):
    """One organisation-level Gmail mailbox and one Telegram bot.

    Sensitive tokens are encrypted before storage; `config` only holds public
    metadata such as the connected address and the temporary OAuth state.
    """

    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("provider", name="uq_integration_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), index=True)  # gmail | telegram
    status: Mapped[str] = mapped_column(String(24), default="not_configured")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_token: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommunicationMessage(Base):
    """An auditable inbox/outbox item linked to a deal when it can be matched."""

    __tablename__ = "communication_messages"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_message_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str] = mapped_column(String(12))  # incoming | outgoing
    external_id: Mapped[str] = mapped_column(String(200), default="")
    sender: Mapped[str] = mapped_column(String(320), default="")
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="sent")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
