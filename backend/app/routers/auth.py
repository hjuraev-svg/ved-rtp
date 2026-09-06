from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import User
from ..realtime import hub
from ..reference import ROLES
from ..schemas import LoginIn, TokenOut, UserCreate, UserOut, UserUpdate
from ..security import (
    create_token,
    current_user,
    get_user_by_email,
    hash_password,
    require_roles,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    return user


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await _authenticate(db, payload.email, payload.password)
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def login_form(
    form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    """OAuth2 password flow so Swagger's Authorize button works."""
    user = await _authenticate(db, form.username, form.password)
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@router.get("/roles")
async def roles():
    return [{"key": k, "name": v} for k, v in ROLES.items()]


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    res = await db.execute(select(User).order_by(User.full_name))
    return res.scalars().all()


async def _active_admin_count(db: AsyncSession, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return (await db.execute(stmt)).scalar_one()


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    if await get_user_by_email(db, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким логином уже существует")
    if payload.role not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестная роль")
    user = User(
        email=payload.email,  # already normalised by the schema validator
        full_name=payload.full_name.strip(),
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await hub.broadcast("user.created", {"user_id": user.id})
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    data = payload.model_dump(exclude_unset=True)

    if data.get("role") is not None and data["role"] not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестная роль")

    # Guard against an admin locking themselves — or everyone — out.
    losing_admin = (
        data.get("is_active") is False
        or (data.get("role") is not None and data["role"] != "admin")
    )
    if user.id == actor.id and losing_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Нельзя снять с себя права администратора или отключить свою учётную запись",
        )
    if user.role == "admin" and user.is_active and losing_admin:
        if await _active_admin_count(db, exclude_id=user.id) == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Это последний активный администратор — сначала назначьте другого",
            )

    if data.get("email") and data["email"] != user.email:
        existing = await get_user_by_email(db, data["email"])
        if existing and existing.id != user.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Пользователь с таким логином уже существует"
            )

    if data.get("password"):
        user.password_hash = hash_password(data["password"])
    data.pop("password", None)

    if data.get("full_name") is not None:
        data["full_name"] = data["full_name"].strip()

    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    # is_active is the one field where False is a meaningful value.
    if "is_active" in data:
        user.is_active = bool(data["is_active"])

    await db.commit()
    await db.refresh(user)
    await hub.broadcast("user.updated", {"user_id": user.id})
    return user
