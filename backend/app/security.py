import hashlib
import hmac
import secrets
from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import LoginSession, TelegramLink, User, utcnow

password_hasher = PasswordHash.recommended()
# Dummy verification prevents disclosing whether an email exists via password-hash timing.
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
COOKIE_NAME = "modus_session"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_db():
    with Session(engine) as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Db) -> User:
    if request.headers.get("X-Bot-Secret") is not None:
        require_bot(request)
        try:
            telegram_id = int(request.headers.get("X-Telegram-Id", ""))
        except ValueError:
            raise HTTPException(401, "Некорректный Telegram ID") from None
        link = db.exec(
            select(TelegramLink).where(TelegramLink.telegram_id == telegram_id)
        ).first()
        user = db.get(User, link.user_id) if link else None
        if not user or not user.is_active:
            raise HTTPException(401, "Привяжите Telegram в кабинете на сайте")
        return user
    bearer = request.headers.get("Authorization", "")
    token = (
        bearer.removeprefix("Bearer ")
        if bearer.startswith("Bearer ")
        else request.cookies.get(COOKIE_NAME)
    )
    login = db.exec(
        select(LoginSession).where(
            LoginSession.token_hash == digest(token or ""),
            LoginSession.expires_at > utcnow(),
        )
    ).first()
    user = db.get(User, login.user_id) if login else None
    if not user or not user.is_active or (bearer and login.telegram_id is None):
        raise HTTPException(401, "Войдите в аккаунт")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def coordinator(user: CurrentUser) -> User:
    if "coordinator" not in user.roles:
        raise HTTPException(403, "Доступно только координатору")
    return user


Coordinator = Annotated[User, Depends(coordinator)]


def create_session(
    db: Session,
    user: User,
    response: Response,
    request: Request,
    telegram_id: int | None = None,
) -> str:
    old = request.cookies.get(COOKIE_NAME)
    if old:
        previous = db.exec(
            select(LoginSession).where(LoginSession.token_hash == digest(old))
        ).first()
        if previous:
            db.delete(previous)
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=digest(token),
            user_id=user.id,
            telegram_id=telegram_id,
            expires_at=utcnow()
            + (timedelta(hours=8) if telegram_id else timedelta(days=7)),
        )
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=8 * 3600 if telegram_id else 7 * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )

    return token


class RateLimiter:
    """Single-process MVP limit, keyed by direct peer (never untrusted forwarding headers)."""

    def __init__(self):
        self.buckets: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    def check(self, key: str, limit: int = 10, window: int = 300) -> None:
        now = monotonic()
        with self.lock:
            for stale in [
                k for k, v in self.buckets.items() if not v or v[-1] <= now - window
            ]:
                del self.buckets[stale]
            bucket = self.buckets[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    429,
                    "Слишком много попыток. Повторите через 5 минут.",
                    headers={"Retry-After": str(window)},
                )
            bucket.append(now)


limiter = RateLimiter()


def limit_auth(request: Request) -> None:
    limiter.check(
        "peer:" + (request.client.host if request.client else "unknown"), limit=100
    )


def require_bot(request: Request) -> None:
    secret = settings.bot_api_secret.get_secret_value()
    supplied = request.headers.get("X-Bot-Secret", "")
    if len(secret) < 32 or not hmac.compare_digest(secret.encode(), supplied.encode()):
        raise HTTPException(401, "Недоступно")
