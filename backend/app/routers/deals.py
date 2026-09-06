from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import (
    ChecklistTemplate,
    Claim,
    Comment,
    Deal,
    DealChecklist,
    DealDocument,
    DocType,
    Quote,
    Stage,
    StageEvent,
    User,
)
from ..realtime import hub
from ..schemas import (
    ChecklistOut,
    ChecklistPatch,
    ClaimIn,
    ClaimOut,
    CommentIn,
    CommentOut,
    DealCreate,
    DealListOut,
    DealMove,
    DealOut,
    DealPipelineChange,
    DealUpdate,
    DocumentOut,
    DocumentPatch,
    EventOut,
    QuoteIn,
    QuoteOut,
    QuoteSelect,
)
from ..reference import PIPELINE_BY_CODE
from ..security import can_edit, current_user
from ..services import (
    OPEN_STATUSES,
    bulk_progress,
    checklist_pct,
    days_since,
    docs_ready_pct,
    next_deal_code,
    serialize_deal,
)

router = APIRouter(prefix="/api/deals", tags=["deals"])


async def _get_deal(db: AsyncSession, deal_id: int) -> Deal:
    res = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = res.unique().scalar_one_or_none()
    if not deal:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сделка не найдена")
    return deal


async def _out(db: AsyncSession, deal: Deal) -> DealOut:
    return DealOut.model_validate(
        serialize_deal(deal, await docs_ready_pct(db, deal.id), await checklist_pct(db, deal.id))
    )


@router.get("", response_model=DealListOut)
async def list_deals(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
    pipeline: str | None = None,
    stage_id: int | None = None,
    group_key: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    assignee_id: int | None = None,
    supplier_id: int | None = None,
    priority: str | None = None,
    overdue_only: bool = False,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: str = "updated_desc",
):
    stmt = select(Deal)

    if pipeline:
        stmt = stmt.where(Deal.pipeline == pipeline)
    if stage_id:
        stmt = stmt.where(Deal.stage_id == stage_id)
    if group_key:
        stmt = stmt.join(Stage, Stage.id == Deal.stage_id).where(Stage.group_key == group_key)
    if status_filter:
        stmt = stmt.where(Deal.status == status_filter)
    else:
        stmt = stmt.where(Deal.status.in_(OPEN_STATUSES))
    if assignee_id:
        stmt = stmt.where(Deal.assignee_id == assignee_id)
    if supplier_id:
        stmt = stmt.where(Deal.supplier_id == supplier_id)
    if priority:
        stmt = stmt.where(Deal.priority == priority)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Deal.title.ilike(like),
                Deal.code.ilike(like),
                Deal.contract_number.ilike(like),
                Deal.gtd_number.ilike(like),
                Deal.unk_number.ilike(like),
                Deal.description.ilike(like),
            )
        )

    order = {
        "updated_desc": Deal.updated_at.desc(),
        "updated_asc": Deal.updated_at.asc(),
        "created_desc": Deal.created_at.desc(),
        "stage_asc": Deal.stage_id.asc(),
        "stage_desc": Deal.stage_id.desc(),
        "oldest_in_stage": Deal.stage_entered_at.asc(),
        "code_asc": Deal.code.asc(),
    }.get(sort, Deal.updated_at.desc())

    total = (
        await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()

    rows = (
        (
            await db.execute(
                stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .unique()
        .scalars()
        .all()
    )

    progress = await bulk_progress(db, [d.id for d in rows])
    items = [
        DealOut.model_validate(serialize_deal(d, *progress.get(d.id, (0, 0)))) for d in rows
    ]
    if overdue_only:
        # Overdue is a computed property, so it is filtered after materialising
        # the page; report the filtered count rather than the pre-filter total.
        items = [i for i in items if i.is_overdue]
        total = len(items)

    return DealListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DealOut, status_code=201)
async def create_deal(
    payload: DealCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    if payload.pipeline not in PIPELINE_BY_CODE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип сделки")

    stages = (
        await db.execute(
            select(Stage).where(Stage.pipeline == payload.pipeline).order_by(Stage.id)
        )
    ).scalars().all()
    if not stages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "У типа сделки нет этапов")

    data = payload.model_dump()
    stage_id = data.pop("stage_id", None)
    if stage_id is None:
        stage_id = stages[0].id
    elif stage_id not in {st.id for st in stages}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Этап не относится к выбранному типу сделки",
        )

    now = datetime.now(timezone.utc)
    deal = Deal(
        **data,
        stage_id=stage_id,
        code=await next_deal_code(db, payload.pipeline),
        status="active",
        stage_entered_at=now,
    )
    if deal.assignee_id is None:
        deal.assignee_id = user.id
    db.add(deal)
    await db.flush()

    # Materialise this deal type's checklist and document set — a local
    # purchase must not inherit ГТД or Order Confirmation.
    templates = (
        await db.execute(
            select(ChecklistTemplate).where(ChecklistTemplate.pipeline == deal.pipeline)
        )
    ).scalars().all()
    db.add_all(DealChecklist(deal_id=deal.id, template_id=t.id) for t in templates)

    doc_types = (
        await db.execute(select(DocType).where(DocType.pipeline == deal.pipeline))
    ).scalars().all()
    db.add_all(DealDocument(deal_id=deal.id, doc_type_id=d.id) for d in doc_types)

    db.add(StageEvent(deal_id=deal.id, to_stage_id=deal.stage_id, user_id=user.id, comment="Создана сделка"))

    await db.commit()
    deal = await _get_deal(db, deal.id)
    await hub.broadcast("deal.created", {"deal_id": deal.id, "code": deal.code})
    return await _out(db, deal)


@router.get("/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    return await _out(db, await _get_deal(db, deal_id))


@router.patch("/{deal_id}", response_model=DealOut)
async def update_deal(
    deal_id: int,
    payload: DealUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    deal = await _get_deal(db, deal_id)
    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] not in ("active", "on_hold", "done", "cancelled"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный статус")

    # First ETA entered becomes the baseline for slip detection.
    if data.get("eta") and not deal.eta_initial and "eta_initial" not in data:
        data["eta_initial"] = data["eta"]

    for key, value in data.items():
        setattr(deal, key, value)

    if data.get("status") in ("done", "cancelled") and deal.closed_at is None:
        deal.closed_at = datetime.now(timezone.utc)
    elif data.get("status") in ("active", "on_hold"):
        deal.closed_at = None

    await db.commit()
    deal = await _get_deal(db, deal_id)
    await hub.broadcast("deal.updated", {"deal_id": deal.id, "code": deal.code})
    return await _out(db, deal)


@router.patch("/{deal_id}/pipeline", response_model=DealOut)
async def change_deal_pipeline(
    deal_id: int,
    payload: DealPipelineChange,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    """Change type while retaining data belonging to the previous type."""
    deal = await _get_deal(db, deal_id)
    if payload.pipeline not in PIPELINE_BY_CODE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип сделки")
    if payload.pipeline == deal.pipeline:
        return await _out(db, deal)

    first_stage = (
        await db.execute(
            select(Stage).where(Stage.pipeline == payload.pipeline).order_by(Stage.id).limit(1)
        )
    ).scalar_one_or_none()
    if not first_stage:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "У типа сделки нет этапов")

    old_pipeline = deal.pipeline
    old_stage_id = deal.stage_id
    old_name = PIPELINE_BY_CODE[old_pipeline]["name"]
    new_name = PIPELINE_BY_CODE[payload.pipeline]["name"]
    now = datetime.now(timezone.utc)

    # Create the target type's checklist and documents only once. Rows from
    # previous types stay intact so progress and uploaded files are not lost.
    existing_templates = set(
        (
            await db.execute(
                select(DealChecklist.template_id).where(DealChecklist.deal_id == deal.id)
            )
        ).scalars()
    )
    templates = (
        await db.execute(
            select(ChecklistTemplate).where(ChecklistTemplate.pipeline == payload.pipeline)
        )
    ).scalars().all()
    db.add_all(
        DealChecklist(deal_id=deal.id, template_id=t.id)
        for t in templates
        if t.id not in existing_templates
    )

    existing_doc_types = set(
        (
            await db.execute(
                select(DealDocument.doc_type_id).where(DealDocument.deal_id == deal.id)
            )
        ).scalars()
    )
    doc_types = (
        await db.execute(select(DocType).where(DocType.pipeline == payload.pipeline))
    ).scalars().all()
    db.add_all(
        DealDocument(deal_id=deal.id, doc_type_id=d.id)
        for d in doc_types
        if d.id not in existing_doc_types
    )

    days_in_old_stage = days_since(deal.stage_entered_at)
    deal.pipeline = payload.pipeline
    deal.code = await next_deal_code(db, payload.pipeline)
    deal.stage_id = first_stage.id
    deal.stage_entered_at = now
    db.add(
        StageEvent(
            deal_id=deal.id,
            from_stage_id=old_stage_id,
            to_stage_id=first_stage.id,
            days_in_from_stage=days_in_old_stage,
            comment=f"Тип сделки изменён: {old_name} → {new_name}",
            user_id=user.id,
            created_at=now,
        )
    )

    await db.commit()
    await db.refresh(deal, attribute_names=["stage"])
    await hub.broadcast(
        "deal.updated",
        {"deal_id": deal.id, "code": deal.code, "pipeline": deal.pipeline},
    )
    return await _out(db, deal)


@router.post("/{deal_id}/move", response_model=DealOut)
async def move_deal(
    deal_id: int,
    payload: DealMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    deal = await _get_deal(db, deal_id)
    target = await db.get(Stage, payload.stage_id)
    if not target:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный этап")
    if target.pipeline != deal.pipeline:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Этап относится к другому типу сделки",
        )
    if payload.stage_id == deal.stage_id:
        return await _out(db, deal)

    now = datetime.now(timezone.utc)
    db.add(
        StageEvent(
            deal_id=deal.id,
            from_stage_id=deal.stage_id,
            to_stage_id=payload.stage_id,
            days_in_from_stage=days_since(deal.stage_entered_at),
            comment=payload.comment,
            user_id=user.id,
            created_at=now,
        )
    )
    deal.stage_id = payload.stage_id
    deal.stage_entered_at = now

    await db.commit()
    await db.refresh(deal, attribute_names=["stage"])
    await hub.broadcast("deal.moved", {"deal_id": deal.id, "stage_id": deal.stage_id})
    return await _out(db, deal)


@router.delete("/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    deal = await _get_deal(db, deal_id)
    await db.delete(deal)
    await db.commit()
    await hub.broadcast("deal.deleted", {"deal_id": deal_id})


# --------------------------------------------------------------------------
# checklist
# --------------------------------------------------------------------------
@router.get("/{deal_id}/checklist", response_model=list[ChecklistOut])
async def get_checklist(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    deal = await _get_deal(db, deal_id)
    rows = (
        (
            await db.execute(
                select(DealChecklist)
                .join(ChecklistTemplate, ChecklistTemplate.id == DealChecklist.template_id)
                .where(
                    DealChecklist.deal_id == deal_id,
                    ChecklistTemplate.pipeline == deal.pipeline,
                )
                .order_by(ChecklistTemplate.order_no)
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [
        ChecklistOut.model_validate(
            {
                "id": r.id,
                "template_id": r.template_id,
                "code": r.template.code,
                "title": r.template.title,
                "section": r.template.section,
                "stage_id": r.template.stage_id,
                "is_done": r.is_done,
                "done_at": r.done_at,
                "done_by_id": r.done_by_id,
                "note": r.note,
            }
        )
        for r in rows
    ]


@router.patch("/{deal_id}/checklist/{item_id}", response_model=ChecklistOut)
async def patch_checklist(
    deal_id: int,
    item_id: int,
    payload: ChecklistPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    row = await db.get(DealChecklist, item_id)
    if not row or row.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пункт чек-листа не найден")

    if payload.is_done is not None and payload.is_done != row.is_done:
        row.is_done = payload.is_done
        row.done_at = datetime.now(timezone.utc) if payload.is_done else None
        row.done_by_id = user.id if payload.is_done else None
    if payload.note is not None:
        row.note = payload.note

    await db.commit()
    await db.refresh(row)
    await hub.broadcast("checklist.updated", {"deal_id": deal_id})
    return ChecklistOut.model_validate(
        {
            "id": row.id,
            "template_id": row.template_id,
            "code": row.template.code,
            "title": row.template.title,
            "section": row.template.section,
            "stage_id": row.template.stage_id,
            "is_done": row.is_done,
            "done_at": row.done_at,
            "done_by_id": row.done_by_id,
            "note": row.note,
        }
    )


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------
@router.get("/{deal_id}/documents", response_model=list[DocumentOut])
async def get_documents(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    deal = await _get_deal(db, deal_id)
    rows = (
        (
            await db.execute(
                select(DealDocument)
                .join(DocType, DocType.id == DealDocument.doc_type_id)
                .where(
                    DealDocument.deal_id == deal_id,
                    DocType.pipeline == deal.pipeline,
                )
                .order_by(DocType.order_no)
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [
        DocumentOut.model_validate(
            {
                "id": r.id,
                "doc_type_id": r.doc_type_id,
                "code": r.doc_type.code,
                "name": r.doc_type.name,
                "is_required": r.doc_type.is_required,
                "is_received": r.is_received,
                "received_at": r.received_at,
                "number": r.number,
                "file_name": r.file_name,
                "note": r.note,
            }
        )
        for r in rows
    ]


@router.patch("/{deal_id}/documents/{doc_id}", response_model=DocumentOut)
async def patch_document(
    deal_id: int,
    doc_id: int,
    payload: DocumentPatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    row = await db.get(DealDocument, doc_id)
    if not row or row.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")

    data = payload.model_dump(exclude_unset=True)
    if data.get("is_received") and not row.received_at and not data.get("received_at"):
        data["received_at"] = datetime.now(timezone.utc).date()
    if data.get("is_received") is False:
        data["received_at"] = None
    for key, value in data.items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    await hub.broadcast("document.updated", {"deal_id": deal_id})
    return DocumentOut.model_validate(
        {
            "id": row.id,
            "doc_type_id": row.doc_type_id,
            "code": row.doc_type.code,
            "name": row.doc_type.name,
            "is_required": row.doc_type.is_required,
            "is_received": row.is_received,
            "received_at": row.received_at,
            "number": row.number,
            "file_name": row.file_name,
            "note": row.note,
        }
    )


# --------------------------------------------------------------------------
# quotes (КП)
# --------------------------------------------------------------------------
@router.get("/{deal_id}/quotes", response_model=list[QuoteOut])
async def get_quotes(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    rows = (
        (await db.execute(select(Quote).where(Quote.deal_id == deal_id).order_by(Quote.price)))
        .unique()
        .scalars()
        .all()
    )
    return rows


@router.post("/{deal_id}/quotes", response_model=QuoteOut, status_code=201)
async def add_quote(
    deal_id: int,
    payload: QuoteIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    await _get_deal(db, deal_id)
    quote = Quote(deal_id=deal_id, **payload.model_dump())
    db.add(quote)
    await db.commit()
    res = await db.execute(select(Quote).where(Quote.id == quote.id))
    await hub.broadcast("quote.added", {"deal_id": deal_id})
    return res.unique().scalar_one()


@router.post("/{deal_id}/quotes/{quote_id}/select", response_model=QuoteOut)
async def select_quote(
    deal_id: int,
    quote_id: int,
    payload: QuoteSelect,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    quote = await db.get(Quote, quote_id)
    if not quote or quote.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "КП не найдено")

    others = (await db.execute(select(Quote).where(Quote.deal_id == deal_id))).unique().scalars().all()
    for q in others:
        q.is_selected = q.id == quote_id
        if q.id != quote_id:
            q.select_reason = ""
    quote.select_reason = payload.select_reason

    # Selecting a КП also fixes the supplier and contract currency on the deal.
    deal = await _get_deal(db, deal_id)
    deal.supplier_id = quote.supplier_id
    if quote.price is not None and deal.contract_amount is None:
        deal.contract_amount = quote.price
    if quote.currency:
        deal.currency = quote.currency
    if quote.incoterms and not deal.incoterms:
        deal.incoterms = quote.incoterms

    await db.commit()
    res = await db.execute(select(Quote).where(Quote.id == quote_id))
    await hub.broadcast("quote.selected", {"deal_id": deal_id})
    return res.unique().scalar_one()


@router.delete("/{deal_id}/quotes/{quote_id}", status_code=204)
async def delete_quote(
    deal_id: int, quote_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(can_edit)
):
    quote = await db.get(Quote, quote_id)
    if not quote or quote.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "КП не найдено")
    await db.delete(quote)
    await db.commit()
    await hub.broadcast("quote.deleted", {"deal_id": deal_id})


# --------------------------------------------------------------------------
# claims / comments / history
# --------------------------------------------------------------------------
@router.get("/{deal_id}/claims", response_model=list[ClaimOut])
async def get_claims(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    res = await db.execute(select(Claim).where(Claim.deal_id == deal_id).order_by(Claim.created_at.desc()))
    return res.scalars().all()


@router.post("/{deal_id}/claims", response_model=ClaimOut, status_code=201)
async def add_claim(
    deal_id: int, payload: ClaimIn, db: AsyncSession = Depends(get_db), _: User = Depends(can_edit)
):
    await _get_deal(db, deal_id)
    claim = Claim(deal_id=deal_id, **payload.model_dump())
    db.add(claim)
    await db.commit()
    await db.refresh(claim)
    await hub.broadcast("claim.added", {"deal_id": deal_id})
    return claim


@router.patch("/{deal_id}/claims/{claim_id}", response_model=ClaimOut)
async def patch_claim(
    deal_id: int,
    claim_id: int,
    payload: ClaimIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    claim = await db.get(Claim, claim_id)
    if not claim or claim.deal_id != deal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Претензия не найдена")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(claim, key, value)
    if claim.status in ("settled", "rejected") and claim.resolved_at is None:
        claim.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(claim)
    await hub.broadcast("claim.updated", {"deal_id": deal_id})
    return claim


@router.get("/{deal_id}/comments", response_model=list[CommentOut])
async def get_comments(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    rows = (
        await db.execute(
            select(Comment, User.full_name)
            .outerjoin(User, User.id == Comment.user_id)
            .where(Comment.deal_id == deal_id)
            .order_by(Comment.created_at.desc())
        )
    ).all()
    return [
        CommentOut.model_validate(
            {
                "id": c.id,
                "deal_id": c.deal_id,
                "user_id": c.user_id,
                "author": name or "—",
                "body": c.body,
                "created_at": c.created_at,
            }
        )
        for c, name in rows
    ]


@router.post("/{deal_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    deal_id: int,
    payload: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(can_edit),
):
    await _get_deal(db, deal_id)
    comment = Comment(deal_id=deal_id, user_id=user.id, body=payload.body)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    await hub.broadcast("comment.added", {"deal_id": deal_id})
    return CommentOut.model_validate(
        {
            "id": comment.id,
            "deal_id": deal_id,
            "user_id": user.id,
            "author": user.full_name,
            "body": comment.body,
            "created_at": comment.created_at,
        }
    )


@router.get("/{deal_id}/history", response_model=list[EventOut])
async def get_history(deal_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    rows = (
        await db.execute(
            select(StageEvent, User.full_name)
            .outerjoin(User, User.id == StageEvent.user_id)
            .where(StageEvent.deal_id == deal_id)
            .order_by(StageEvent.created_at.desc())
        )
    ).all()
    stages = {s.id: s.name for s in (await db.execute(select(Stage))).scalars().all()}
    return [
        EventOut.model_validate(
            {
                "id": e.id,
                "deal_id": e.deal_id,
                "from_stage_id": e.from_stage_id,
                "to_stage_id": e.to_stage_id,
                "from_stage_name": stages.get(e.from_stage_id, ""),
                "to_stage_name": stages.get(e.to_stage_id, ""),
                "days_in_from_stage": e.days_in_from_stage,
                "comment": e.comment,
                "user_id": e.user_id,
                "author": name or "система",
                "created_at": e.created_at,
            }
        )
        for e, name in rows
    ]
