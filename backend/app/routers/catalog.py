from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import ChecklistTemplate, DocType, Stage, Supplier, User
from ..realtime import hub
from ..reference import GROUPS, PIPELINES, TRANSPORT_MODES
from ..schemas import StageOut, StageUpdate, SupplierIn, SupplierOut
from ..security import can_edit, current_user, require_roles

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/pipelines")
async def list_pipelines(_: User = Depends(current_user)):
    """The three deal types. `code` is what Deal.pipeline stores."""
    return PIPELINES


@router.get("/stages", response_model=list[StageOut])
async def list_stages(
    pipeline: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(Stage).order_by(Stage.id)
    if pipeline:
        stmt = stmt.where(Stage.pipeline == pipeline)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.patch("/stages/{stage_id}", response_model=StageOut)
async def update_stage(
    stage_id: int,
    payload: StageUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "director")),
):
    stage = await db.get(Stage, stage_id)
    if not stage:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Этап не найден")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(stage, key, value)
    await db.commit()
    await db.refresh(stage)
    await hub.broadcast("stage.updated", {"stage_id": stage_id})
    return stage


@router.get("/groups")
async def list_groups(_: User = Depends(current_user)):
    return GROUPS


@router.get("/transport-modes")
async def transport_modes(_: User = Depends(current_user)):
    return [{"key": k, "name": v} for k, v in TRANSPORT_MODES.items()]


@router.get("/checklist-template")
async def checklist_template(
    pipeline: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(ChecklistTemplate).order_by(ChecklistTemplate.order_no)
    if pipeline:
        stmt = stmt.where(ChecklistTemplate.pipeline == pipeline)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": r.id, "code": r.code, "title": r.title, "section": r.section,
         "stage_id": r.stage_id, "pipeline": r.pipeline}
        for r in rows
    ]


@router.get("/doc-types")
async def doc_types(
    pipeline: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(DocType).order_by(DocType.order_no)
    if pipeline:
        stmt = stmt.where(DocType.pipeline == pipeline)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": r.id, "code": r.code, "name": r.name,
         "is_required": r.is_required, "pipeline": r.pipeline}
        for r in rows
    ]


# ---------------- suppliers ----------------
@router.get("/suppliers", response_model=list[SupplierOut])
async def list_suppliers(
    include_inactive: bool = False,
    category: str = "",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(Supplier).order_by(Supplier.category, Supplier.name)
    if not include_inactive:
        stmt = stmt.where(Supplier.is_active.is_(True))
    if category:
        stmt = stmt.where(Supplier.category == category)
    return (await db.execute(stmt)).scalars().all()


@router.get("/supplier-categories", response_model=list[str])
async def list_supplier_categories(
    db: AsyncSession = Depends(get_db), _: User = Depends(current_user)
):
    """Categories actually in use — fills the filter without a separate table."""
    rows = await db.execute(
        select(Supplier.category)
        .where(Supplier.category != "")
        .distinct()
        .order_by(Supplier.category)
    )
    return list(rows.scalars().all())


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
async def create_supplier(
    payload: SupplierIn, db: AsyncSession = Depends(get_db), _: User = Depends(can_edit)
):
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    await hub.broadcast("supplier.created", {"supplier_id": supplier.id})
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: int,
    payload: SupplierIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(can_edit),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поставщик не найден")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, key, value)
    await db.commit()
    await db.refresh(supplier)
    await hub.broadcast("supplier.updated", {"supplier_id": supplier_id})
    return supplier
