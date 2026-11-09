import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID

import pytest
from app.config import settings
from app.database import engine
from app.main import app
from app.models import Notification, TelegramLink, TelegramLinkToken, User, utcnow
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session, select

from tests.helpers import HEADERS
from tests.test_discussion import send
from tests.test_work_queue import assign

TOKEN = "123456789:" + "a" * 35
SECRET = "offline-test-service-secret-123456789"
TG_ID = 5000000001


def signed(telegram_id=TG_ID, age=0, **overrides):
    values = {
        "auth_date": str(int(utcnow().timestamp()) - age),
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Проверка"}, ensure_ascii=False
        ),
        **overrides,
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    key = hmac.digest(b"WebAppData", TOKEN.encode(), "sha256")
    return urlencode(
        {**values, "hash": hmac.new(key, check.encode(), hashlib.sha256).hexdigest()}
    )


def token_for(client):
    response = client.post("/telegram/link")
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["url"]).query)["start"][0][5:]


@pytest.fixture()
def telegram(team, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "bot_api_secret", SecretStr(SECRET))
    monkeypatch.setattr(settings, "bot_username", "ModusOfflineTestBot")
    monkeypatch.setattr(settings, "mini_app_url", "https://modus.example.com")
    with TestClient(app, headers={**HEADERS, "X-Bot-Secret": SECRET}) as service:
        yield team, service


def bind(client, service, telegram_id=TG_ID):
    return service.post(
        "/internal/telegram/bind",
        json={"token": token_for(client), "telegram_id": telegram_id},
    )


def test_link_single_use_hash_and_replacement(telegram):
    team, service = telegram
    author = team["author"]
    old = token_for(author)
    token = token_for(author)
    with Session(engine) as db:
        records = db.exec(select(TelegramLinkToken)).all()
        assert len(records) == 1 and records[0].token_hash != token
    assert (
        service.post(
            "/internal/telegram/bind", json={"token": old, "telegram_id": TG_ID}
        ).status_code
        == 400
    )
    result = service.post(
        "/internal/telegram/bind", json={"token": token, "telegram_id": TG_ID}
    )
    assert result.status_code == 200 and result.json()["id"] == team["author_id"]
    assert (
        service.post(
            "/internal/telegram/bind", json={"token": token, "telegram_id": TG_ID}
        ).status_code
        == 400
    )
    assert author.get("/telegram/status").json()["linked"]
    assert author.post("/telegram/link").status_code == 409
    assert bind(team["first"], service).status_code == 409


def test_expired_link_and_missing_service_secret(telegram):
    team, service = telegram
    token = token_for(team["author"])
    with Session(engine) as db:
        row = db.exec(select(TelegramLinkToken)).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()
    assert (
        service.post(
            "/internal/telegram/bind", json={"token": token, "telegram_id": TG_ID}
        ).status_code
        == 400
    )
    assert (
        team["author"]
        .post("/internal/telegram/bind", json={"token": token, "telegram_id": TG_ID})
        .status_code
        == 401
    )
    assert (
        team["author"]
        .get("/auth/me", headers={"X-Bot-Secret": "wrong", "X-Telegram-Id": str(TG_ID)})
        .status_code
        == 401
    )


def test_mini_auth_bearer_cookie_logout_unlink(telegram):
    team, service = telegram
    assert bind(team["author"], service).status_code == 200
    with TestClient(app, headers=HEADERS) as mini:
        result = mini.post("/telegram/auth", json={"init_data": signed()})
        assert result.status_code == 200, result.text
        assert result.json()["user"]["id"] == team["author_id"]
        bearer = {"Authorization": "Bearer " + result.json()["access_token"]}
        mini.cookies.clear()  # Telegram Web may block third-party cookies.
        assert mini.get("/auth/me", headers=bearer).status_code == 200
        assert mini.get("/appeals", headers=bearer).json()["total"] == 1
        download = team["appeal"]["attachments"][0]["download_url"].removeprefix("/api")
        assert mini.get(download, headers=bearer).status_code == 200
        assert mini.post("/auth/logout", headers=bearer).status_code == 204
        assert mini.get("/auth/me", headers=bearer).status_code == 401
        result = mini.post("/telegram/auth", json={"init_data": signed()})
        bearer = {"Authorization": "Bearer " + result.json()["access_token"]}
        assert team["author"].delete("/telegram/link").status_code == 204
        mini.cookies.clear()
        assert mini.get("/auth/me", headers=bearer).status_code == 401
        assert team["author"].get("/auth/me").status_code == 200
        assert (
            mini.post("/telegram/auth", json={"init_data": signed()}).status_code == 403
        )
    assert (
        service.get("/auth/me", headers={"X-Telegram-Id": str(TG_ID)}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "data",
    [
        lambda: signed(age=3600),
        lambda: signed(age=-120),
        lambda: signed(chat_type="group"),
        lambda: signed(telegram_id="5000000001"),
        lambda: signed().replace("hash=", "hash=bad"),
        lambda: signed() + "&auth_date=1",
    ],
)
def test_mini_rejects_forged_stale_or_ambiguous_data(telegram, data):
    team, _ = telegram
    response = team["author"].post("/telegram/auth", json={"init_data": data()})
    assert response.status_code == 401, response.text


def test_bot_uses_shared_permissions_and_durable_state(telegram):
    team, service = telegram
    assert bind(team["first"], service).status_code == 200
    identity = {"X-Telegram-Id": str(TG_ID)}
    path = f"/appeals/{team['appeal']['id']}"
    assert service.get(path, headers=identity).status_code == 404
    assert assign(team).status_code == 200
    assert service.get(path, headers=identity).status_code == 200
    assert (
        service.post(
            "/admin/companies", headers=identity, json={"name": "Запрещено"}
        ).status_code
        == 403
    )
    draft = {"mode": "reply", "appeal_id": team["appeal"]["id"]}
    assert (
        service.put(
            "/internal/telegram/state", headers=identity, json={"value": draft}
        ).status_code
        == 200
    )
    with TestClient(
        app, headers={**HEADERS, "X-Bot-Secret": SECRET, **identity}
    ) as restarted:
        assert restarted.get("/internal/telegram/state").json()["value"] == draft
    with Session(engine) as db:
        user = db.get(User, UUID(team["first_id"]))
        user.is_active = False
        db.add(user)
        db.commit()
    assert service.get(path, headers=identity).status_code == 401


def test_delivery_leases_ack_retry_and_blocked(telegram):
    team, service = telegram
    assert bind(team["first"], service).status_code == 200
    assert assign(team).status_code == 200
    jobs = service.post("/internal/telegram/deliveries").json()
    assert len(jobs) == 1, jobs
    job = jobs[0]
    assert job["telegram_id"] == TG_ID
    assert job["url"] == f"https://modus.example.com/mini/queue/{team['appeal']['id']}"
    assert service.post("/internal/telegram/deliveries").json() == []
    path = f"/internal/telegram/deliveries/{job['id']}"
    assert (
        service.post(path, json={"claim": job["claim"], "outcome": "sent"}).status_code
        == 204
    )
    assert (
        service.post(path, json={"claim": job["claim"], "outcome": "sent"}).status_code
        == 409
    )
    assert send(team).status_code == 201
    job = service.post("/internal/telegram/deliveries").json()[0]
    path = f"/internal/telegram/deliveries/{job['id']}"
    assert (
        service.post(path, json={"claim": job["claim"], "outcome": "retry"}).status_code
        == 204
    )
    assert service.post("/internal/telegram/deliveries").json() == []
    with Session(engine) as db:
        row = db.get(Notification, UUID(job["id"]))
        row.telegram_lease_until = utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()
    new = service.post("/internal/telegram/deliveries").json()[0]
    assert new["claim"] != job["claim"]
    assert (
        service.post(
            path, json={"claim": new["claim"], "outcome": "blocked"}
        ).status_code
        == 204
    )
    assert send(team).status_code == 201
    assert service.post("/internal/telegram/deliveries").json() == []
    with Session(engine) as db:
        assert not db.exec(select(TelegramLink)).one().delivery_enabled


def test_concurrent_single_identity_cannot_bind_two_users(telegram):
    team, _ = telegram
    tokens = [token_for(team["author"]), token_for(team["first"])]

    def run(token):
        with TestClient(app, headers={**HEADERS, "X-Bot-Secret": SECRET}) as client:
            return client.post(
                "/internal/telegram/bind", json={"token": token, "telegram_id": TG_ID}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, tokens)) == [200, 409]


def test_telegram_not_configured_leaves_site_working(team):
    assert team["author"].get("/telegram/status").json() == {
        "configured": False,
        "linked": False,
        "delivery_enabled": False,
    }
    assert team["author"].post("/telegram/link").status_code == 503
    assert team["author"].get("/appeals").status_code == 200


def test_inflight_blocked_ack_does_not_disable_new_binding(telegram):
    team, service = telegram
    assert bind(team["first"], service).status_code == 200
    assert assign(team).status_code == 200
    job = service.post("/internal/telegram/deliveries").json()[0]
    assert team["first"].delete("/telegram/link").status_code == 204
    assert bind(team["first"], service, telegram_id=TG_ID + 1).status_code == 200
    assert (
        service.post(
            f"/internal/telegram/deliveries/{job['id']}",
            json={"claim": job["claim"], "outcome": "blocked"},
        ).status_code
        == 204
    )
    assert team["first"].get("/telegram/status").json()["delivery_enabled"]
