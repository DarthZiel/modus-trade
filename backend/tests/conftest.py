"""Isolated PostgreSQL fixtures shared by account and appeal integration tests."""

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from app.database import engine
from app.main import app
from app.models import Company, Department, User
from app.security import limiter, password_hasher
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from tests.helpers import HEADERS, PASSWORD, invite, token_from
from tests.test_appeals import png, submit


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database():
    assert settings.db_name.endswith("_test"), (
        "Refusing to run destructive tests outside a *_test database"
    )
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture()
def setup():
    with Session(engine) as db:
        for table in reversed(SQLModel.metadata.sorted_tables):
            db.execute(table.delete())
        company = Company(name="Тестовая компания")
        db.add(company)
        db.flush()
        department = Department(company_id=company.id, name="Склад")
        db.add(department)
        db.flush()
        admin = User(
            name="Координатор",
            email="admin@example.com",
            password_hash=password_hasher.hash(PASSWORD),
            company_id=company.id,
            department_id=department.id,
            roles=["employee", "coordinator"],
        )
        db.add(admin)
        db.commit()
        ids = {
            "company_id": str(company.id),
            "department_id": str(department.id),
            "admin_id": str(admin.id),
        }
    limiter.buckets.clear()
    with TestClient(app, headers=HEADERS) as client:
        assert (
            client.post(
                "/auth/login", json={"email": "ADMIN@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        yield client, ids


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")


@pytest.fixture()
def team(setup):
    admin, ids = setup
    clients = []

    def member(email, roles):
        token = token_from(invite(admin, ids, email=email, roles=roles))
        client = TestClient(app, headers=HEADERS)
        clients.append(client)
        response = client.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        )
        assert response.status_code == 201
        return client, response.json()["id"]

    author, author_id = member("author@example.com", ["employee"])
    first, first_id = member("first@example.com", ["responsible"])
    second, second_id = member("second@example.com", ["responsible"])
    result = submit(author, files=[("test.png", png(), "image/png")])
    assert result.status_code == 201
    yield {
        "admin": admin,
        "author": author,
        "author_id": author_id,
        "first": first,
        "first_id": first_id,
        "second": second,
        "second_id": second_id,
        "appeal": result.json(),
        "ids": ids,
    }
    for client in clients:
        client.close()
