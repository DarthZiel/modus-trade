import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, text
from sqlmodel import select

from app.config import settings
from app.models import (
    Appeal,
    LoginSession,
    Notification,
    TelegramLink,
    TelegramLinkToken,
    User,
    utcnow,
)
from app.notifications import visible
from app.schemas import UserPublic
from app.security import (
    CurrentUser,
    Db,
    create_session,
    digest,
    limit_auth,
    limiter,
    require_bot,
)

router = APIRouter(prefix="/telegram", tags=["Telegram"])
internal = APIRouter(
    prefix="/internal/telegram",
    tags=["Bot service"],
    dependencies=[Depends(require_bot)],
)


def configured() -> bool:
    return bool(
        settings.bot_token.get_secret_value()
        and len(settings.bot_api_secret.get_secret_value()) >= 32
        and re.fullmatch(r"[A-Za-z0-9_]{5,32}", settings.bot_username)
        and settings.mini_app_url.startswith("https://")
    )


class LinkStatus(BaseModel):
    configured: bool
    linked: bool
    delivery_enabled: bool = False


@router.get("/status")
def status(user: CurrentUser, db: Db) -> LinkStatus:
    link = db.exec(select(TelegramLink).where(TelegramLink.user_id == user.id)).first()
    return LinkStatus(
        configured=configured(),
        linked=bool(link),
        delivery_enabled=bool(link and link.delivery_enabled),
    )


class LinkCreated(BaseModel):
    url: str
    expires_at: datetime


@router.post("/link")
def link_token(user: CurrentUser, db: Db) -> LinkCreated:
    if not configured():
        raise HTTPException(503, "Telegram ещё не настроен администратором")
    # Serialize against link, unlink and competing token requests for this account.
    db.exec(select(User).where(User.id == user.id).with_for_update()).one()
    if db.exec(select(TelegramLink).where(TelegramLink.user_id == user.id)).first():
        raise HTTPException(409, "Telegram уже привязан")
    db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == user.id))
    token = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(minutes=10)
    db.add(
        TelegramLinkToken(user_id=user.id, token_hash=digest(token), expires_at=expires)
    )
    db.commit()
    return LinkCreated(
        url=f"https://t.me/{settings.bot_username}?start=link_{token}",
        expires_at=expires,
    )


@router.delete("/link", status_code=204)
def unlink(user: CurrentUser, db: Db):
    db.exec(select(User).where(User.id == user.id).with_for_update()).one()
    db.execute(delete(TelegramLink).where(TelegramLink.user_id == user.id))
    db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == user.id))
    db.execute(
        delete(LoginSession).where(
            LoginSession.user_id == user.id, LoginSession.telegram_id.is_not(None)
        )
    )
    db.commit()


class BindInput(BaseModel):
    token: str = Field(min_length=32, max_length=64)
    telegram_id: int = Field(gt=0, le=2**52 - 1)


@internal.post("/bind")
def bind(data: BindInput, db: Db) -> UserPublic:
    # One Telegram identity cannot be bound concurrently to two accounts.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"telegram:{data.telegram_id}"},
    )
    token = db.exec(
        select(TelegramLinkToken).where(
            TelegramLinkToken.token_hash == digest(data.token)
        )
    ).first()
    if not token:
        raise HTTPException(
            400, "Ссылка недействительна. Создайте новую в кабинете на сайте."
        )
    user = db.exec(select(User).where(User.id == token.user_id).with_for_update()).one()
    token = db.exec(
        select(TelegramLinkToken)
        .where(TelegramLinkToken.token_hash == digest(data.token))
        .execution_options(populate_existing=True)
    ).first()
    if not token:
        raise HTTPException(400, "Ссылка уже использована или заменена")
    if token.expires_at <= utcnow() or not user.is_active:
        raise HTTPException(400, "Срок ссылки истёк или аккаунт недоступен")
    existing = db.exec(
        select(TelegramLink).where(
            or_(
                TelegramLink.user_id == user.id,
                TelegramLink.telegram_id == data.telegram_id,
            )
        )
    ).first()
    if existing:
        raise HTTPException(
            409,
            "Аккаунт или Telegram уже привязан. Сначала отключите старую привязку на сайте.",
        )
    db.add(TelegramLink(user_id=user.id, telegram_id=data.telegram_id))
    db.delete(token)
    db.commit()
    return UserPublic.model_validate(user)


def validate_init_data(raw: str) -> int:
    try:
        pairs = parse_qsl(
            raw, keep_blank_values=True, strict_parsing=True, max_num_fields=30
        )
        values = dict(pairs)
        if len(values) != len(pairs) or not settings.bot_token.get_secret_value():
            raise ValueError
        supplied = values.pop("hash")
        check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
        secret = hmac.digest(
            b"WebAppData", settings.bot_token.get_secret_value().encode(), "sha256"
        )
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        age = utcnow().timestamp() - int(values["auth_date"])
        if not -30 <= age <= 300:
            raise ValueError
        telegram_id = json.loads(values["user"])["id"]
        if type(telegram_id) is not int or not 0 < telegram_id < 2**52:
            raise ValueError
        if values.get("chat_type", "private") != "private":
            raise ValueError
        return telegram_id
    except (ValueError, KeyError, TypeError, OverflowError):
        raise HTTPException(
            401,
            "Данные Telegram недействительны или устарели. Откройте Mini App заново.",
        ) from None


class MiniSession(BaseModel):
    user: UserPublic
    access_token: str


class MiniLogin(BaseModel):
    init_data: str = Field(min_length=1, max_length=16384)


@router.post("/auth", dependencies=[Depends(limit_auth)])
def mini_login(
    data: MiniLogin, request: Request, response: Response, db: Db
) -> MiniSession:
    telegram_id = validate_init_data(data.init_data)
    limiter.check(f"telegram-login:{telegram_id}", limit=20)
    link = db.exec(
        select(TelegramLink)
        .where(TelegramLink.telegram_id == telegram_id)
        .with_for_update()
    ).first()
    user = db.get(User, link.user_id) if link else None
    if not user or not user.is_active:
        raise HTTPException(
            403,
            "Сначала войдите на сайт по приглашению и привяжите Telegram в кабинете.",
        )
    token = create_session(db, user, response, request, telegram_id=telegram_id)
    db.commit()
    return MiniSession(user=UserPublic.model_validate(user), access_token=token)


class BotState(BaseModel):
    value: dict = Field(default_factory=dict)


def own_link(user: User, db):
    link = db.exec(select(TelegramLink).where(TelegramLink.user_id == user.id)).first()
    if not link:
        raise HTTPException(401, "Привяжите Telegram на сайте")
    return link


@internal.get("/state")
def get_state(user: CurrentUser, db: Db) -> BotState:
    return BotState(value=own_link(user, db).state)


@internal.put("/state")
def put_state(data: BotState, user: CurrentUser, db: Db) -> BotState:
    if len(json.dumps(data.value)) > 40000:
        raise HTTPException(422, "Слишком большой черновик")
    link = own_link(user, db)
    link.state = data.value
    db.add(link)
    db.commit()
    return data


class Delivery(BaseModel):
    id: UUID
    claim: UUID
    telegram_id: int
    text: str
    url: str
    appeal_id: int


@internal.post("/deliveries")
def deliveries(db: Db) -> list[Delivery]:
    if not configured():
        return []
    now = utcnow()
    rows = db.exec(
        select(Notification, TelegramLink, User)
        .join(TelegramLink, TelegramLink.user_id == Notification.user_id)
        .join(User, User.id == Notification.user_id)
        .where(
            User.is_active,
            TelegramLink.delivery_enabled,
            Notification.created_at >= TelegramLink.created_at,
            Notification.telegram_sent_at.is_(None),
            Notification.telegram_attempts < 5,
            or_(
                Notification.telegram_lease_until.is_(None),
                Notification.telegram_lease_until < now,
            ),
        )
        .order_by(Notification.created_at)
        .limit(20)
        .with_for_update(skip_locked=True, of=Notification)
    ).all()
    result = []
    for item, link, user in rows:
        if not db.exec(visible(user).where(Notification.id == item.id)).first():
            item.telegram_attempts = 5
            db.add(item)
            continue
        item.telegram_link_id = link.id
        item.telegram_claim = uuid4()
        item.telegram_attempts += 1
        item.telegram_lease_until = now + timedelta(minutes=5)
        db.add(item)
        appeal = db.get(Appeal, item.appeal_id)
        prefix = "appeals" if appeal.author_id == user.id else "queue"
        result.append(
            Delivery(
                id=item.id,
                claim=item.telegram_claim,
                telegram_id=link.telegram_id,
                text=f"{item.title}\nMT-{item.appeal_id:06}",
                url=f"{settings.mini_app_url.rstrip('/')}/mini/{prefix}/{item.appeal_id}",
                appeal_id=item.appeal_id,
            )
        )
    db.commit()
    return result


class Acknowledgement(BaseModel):
    claim: UUID
    outcome: Literal["sent", "retry", "blocked"]


@internal.post("/deliveries/{notification_id}", status_code=204)
def acknowledge(notification_id: UUID, data: Acknowledgement, db: Db):
    item = db.exec(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).first()
    if not item or item.telegram_claim != data.claim:
        raise HTTPException(409, "Срок доставки изменился")
    if data.outcome == "sent":
        item.telegram_sent_at = utcnow()
    elif data.outcome == "blocked":
        link = db.exec(
            select(TelegramLink).where(TelegramLink.user_id == item.user_id)
        ).first()
        if link and link.id == item.telegram_link_id:
            link.delivery_enabled = False
            db.add(link)
    item.telegram_claim = None
    db.add(item)
    db.commit()
