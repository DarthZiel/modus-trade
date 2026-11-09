"""Integration tests. Run only against an isolated PostgreSQL *_test database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

from app.database import engine
from app.main import app
from app.models import (
    Invitation,
    LoginSession,
    User,
    utcnow,
)
from app.security import COOKIE_NAME, digest, limiter, password_hasher
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.helpers import HEADERS, PASSWORD, invite, token_from


def test_invitation_lifecycle_and_permissions(setup):
    admin, ids = setup
    response = invite(admin, ids)
    token = token_from(response)
    with TestClient(app, headers=HEADERS) as worker:
        preview = worker.post("/auth/invitation", json={"token": token})
        assert preview.status_code == 200
        assert preview.json()["department"] == "Склад"
        accepted = worker.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        )
        assert accepted.status_code == 201
        assert "password_hash" not in accepted.json()
        assert "HttpOnly" in accepted.headers["set-cookie"]
        assert "SameSite=lax" in accepted.headers["set-cookie"]
        assert worker.get("/auth/me").json()["email"] == "worker@example.com"
        for path in ("/admin/users", "/admin/invitations"):
            assert worker.get(path).status_code == 403
        assert (
            worker.post("/admin/invitations", json=response.json()).status_code == 403
        )
        assert (
            worker.post(
                "/auth/accept", json={"token": token, "password": PASSWORD}
            ).status_code
            == 410
        )
        old_cookie = worker.cookies.get(COOKIE_NAME)
        assert worker.post("/auth/logout").status_code == 204
        worker.cookies.set(COOKIE_NAME, old_cookie)
        assert worker.get("/auth/me").status_code == 401
    with Session(engine) as db:
        stored = db.exec(select(User).where(User.email == "worker@example.com")).one()
        invitation = db.get(Invitation, UUID(response.json()["id"]))
        assert stored.password_hash != PASSWORD
        assert password_hasher.verify(PASSWORD, stored.password_hash)
        assert invitation.token_hash == digest(token)
        assert token not in str(invitation.model_dump())


def test_revoked_and_expired_invites(setup):
    admin, ids = setup
    response = invite(admin, ids)
    token = token_from(response)
    assert (
        admin.post(f"/admin/invitations/{response.json()['id']}/revoke").status_code
        == 200
    )
    assert (
        admin.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 410
    )
    response = invite(admin, ids)
    token = token_from(response)
    with Session(engine) as db:
        invitation = db.get(Invitation, UUID(response.json()["id"]))
        invitation.expires_at = utcnow() - timedelta(seconds=1)
        db.add(invitation)
        db.commit()
    assert admin.post("/auth/invitation", json={"token": token}).status_code == 410
    assert (
        admin.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 410
    )


def test_blocking_invalidates_existing_sessions(setup):
    admin, ids = setup
    token = token_from(invite(admin, ids, roles=["responsible"]))
    with TestClient(app, headers=HEADERS) as worker:
        user = worker.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        ).json()
        assert set(user["roles"]) == {"employee", "responsible"}
        assert (
            admin.patch(
                "/admin/users/" + user["id"],
                json={"roles": ["responsible"], "is_active": False},
            ).status_code
            == 200
        )
        assert worker.get("/auth/me").status_code == 401
        assert (
            worker.post(
                "/auth/login", json={"email": user["email"], "password": PASSWORD}
            ).status_code
            == 401
        )
        admin.patch(
            "/admin/users/" + user["id"],
            json={"roles": ["employee"], "is_active": True},
        )
        # Unblocking must not revive an old session.
        assert worker.get("/auth/me").status_code == 401
        assert (
            worker.post(
                "/auth/login", json={"email": user["email"], "password": PASSWORD}
            ).status_code
            == 200
        )


def test_last_coordinator_and_role_changes(setup):
    admin, ids = setup
    assert (
        admin.patch(
            "/admin/users/" + ids["admin_id"],
            json={"roles": ["employee"], "is_active": True},
        ).status_code
        == 409
    )
    assert (
        admin.patch(
            "/admin/users/" + ids["admin_id"],
            json={"roles": ["coordinator"], "is_active": False},
        ).status_code
        == 409
    )
    token = token_from(invite(admin, ids))
    with TestClient(app, headers=HEADERS) as worker:
        user_id = worker.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        ).json()["id"]
        assert worker.get("/admin/users").status_code == 403
        assert (
            admin.patch(
                "/admin/users/" + user_id,
                json={"roles": ["coordinator", "responsible"], "is_active": True},
            ).status_code
            == 200
        )
        assert worker.get("/admin/users").status_code == 200
        assert (
            admin.patch(
                "/admin/users/" + user_id,
                json={"roles": ["employee"], "is_active": True},
            ).status_code
            == 200
        )
        assert worker.get("/admin/users").status_code == 403


def test_invite_validation_and_duplicates(setup):
    admin, ids = setup
    assert invite(admin, ids, email="not-email").status_code == 422
    assert invite(admin, ids, roles=["superuser"]).status_code == 422
    assert invite(admin, ids, name="   ").status_code == 422
    assert invite(admin, ids, expires_in_days=0).status_code == 422
    assert invite(admin, ids, department_id=str(uuid4())).status_code == 422
    assert invite(admin, ids, company_id=str(uuid4())).status_code == 422
    assert invite(admin, ids, email="admin@example.com").status_code == 409
    token = token_from(invite(admin, ids, email=" Worker@EXAMPLE.com "))
    assert invite(admin, ids).status_code == 409
    assert (
        admin.post(
            "/auth/accept", json={"token": token, "password": "short"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        ).status_code
        == 201
    )
    assert admin.post("/auth/logout").status_code == 204


def test_csrf_and_session_expiration(setup):
    admin, _ids = setup
    with TestClient(app) as anonymous:
        assert anonymous.get("/admin/users").status_code == 401
        assert (
            anonymous.post(
                "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
            ).status_code
            == 403
        )
    cookie = admin.cookies.get(COOKIE_NAME)
    with Session(engine) as db:
        session = db.exec(
            select(LoginSession).where(LoginSession.token_hash == digest(cookie))
        ).one()
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.add(session)
        db.commit()
    assert admin.get("/auth/me").status_code == 401


def test_concurrent_accept_is_single_use(setup):
    admin, ids = setup
    token = token_from(invite(admin, ids))

    def accept(_):
        with TestClient(app, headers=HEADERS) as worker:
            return worker.post(
                "/auth/accept", json={"token": token, "password": PASSWORD}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept, range(2))) == [201, 410]


def test_directory_scope_and_creation(setup):
    admin, ids = setup
    other = admin.post("/admin/companies", json={"name": "Казахстан"})
    assert other.status_code == 201
    assert admin.post("/admin/companies", json={"name": "Казахстан"}).status_code == 409
    assert (
        admin.post(
            "/admin/departments",
            json={"name": "Продажи", "company_id": other.json()["id"]},
        ).status_code
        == 201
    )
    token = token_from(invite(admin, ids))
    with TestClient(app, headers=HEADERS) as worker:
        worker.post("/auth/accept", json={"token": token, "password": PASSWORD})
        assert len(worker.get("/directory/companies").json()) == 1
        assert len(worker.get("/directory/departments").json()) == 1
        assert worker.post("/admin/companies", json={"name": "Нет"}).status_code == 403


def test_login_throttle_and_wrong_password(setup):
    _admin, _ids = setup
    limiter.buckets.clear()
    with TestClient(app, headers=HEADERS) as client:
        for _ in range(10):
            assert (
                client.post(
                    "/auth/login",
                    json={"email": "admin@example.com", "password": "wrong"},
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
            ).status_code
            == 429
        )
