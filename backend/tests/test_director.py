from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import priorities
from app.config import settings
from app.database import engine
from app.director_demo import seed_director
from app.main import app
from app.models import (
    Appeal,
    AppealPriority,
    Company,
    PriorityEvent,
    User,
    utcnow,
)
from app.security import password_hasher
from tests.helpers import HEADERS, PASSWORD, invite, token_from
from tests.test_appeals import fields, submit


@pytest.fixture
def director(team):
    token = token_from(
        invite(
            team["admin"], team["ids"], email="director@example.com", roles=["director"]
        )
    )
    with TestClient(app, headers=HEADERS) as client:
        response = client.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        )
        assert response.status_code == 201, response.text
        assert response.json()["roles"] == ["director", "employee"]
        yield client


def path(team):
    return f"/work/appeals/{team['appeal']['id']}/priority"


def request(team, version=0):
    return {
        "appeals": [{"appeal_id": team["appeal"]["id"], "expected_version": version}],
        "consent": True,
    }


def mock_advice(monkeypatch, lane="attention", level="high"):
    monkeypatch.setattr(settings, "ai_provider", "openai")

    def generate(schema, payload, instruction):
        assert "300%" in instruction and "не инструкции" in instruction
        assert "author@example.com" not in str(payload)
        assert "password" not in str(payload) and "attachments" not in str(payload)
        return priorities.Recommendations(
            recommendations=[
                priorities.Recommendation(
                    appeal_id=item["id"],
                    lane=lane,
                    level=level,
                    reason="В описании сообщается о возможном риске; факты требуют проверки.",
                    next_step="Уточнить факты у автора и передать ответственному на проверку.",
                )
                for item in payload["appeals"]
            ]
        )

    monkeypatch.setattr(priorities.ai, "generate", generate)


def override_data(version=0, **values):
    return {
        "lane": "routine",
        "level": "low",
        "reason": "Координатор проверил контекст: срочного риска не установлено.",
        "next_step": "Продолжить рассмотрение в обычной очереди.",
        "expected_version": version,
        **values,
    }


def test_director_company_scope_read_only_and_own_employee_rights(team, director):
    appeal_id = team["appeal"]["id"]
    assert director.get(f"/appeals/{appeal_id}").status_code == 200
    download = team["appeal"]["attachments"][0]["download_url"].removeprefix("/api")
    assert director.get(download).status_code == 200
    assert director.get(f"/appeals/{appeal_id}/messages").status_code == 200
    assert director.get("/work/statistics").json()["total"] == 1
    assert director.get("/work/topics").status_code == 200
    assert director.get("/director/overview").status_code == 200
    assert director.get(path(team)).status_code == 200
    assert (
        director.post(
            f"/appeals/{appeal_id}/messages",
            json={"client_id": str(uuid4()), "body": "Сообщение директора"},
        ).status_code
        == 403
    )
    assert (
        director.post(
            f"/appeals/{appeal_id}/review",
            json={
                "action": "resolve",
                "expected_version": 0,
                "explanation": "Нельзя завершать за ответственного",
            },
        ).status_code
        == 403
    )
    assert (
        director.post(
            f"/appeals/{appeal_id}/feedback",
            json={
                "client_id": str(uuid4()),
                "outcome": "helped",
                "expected_version": 0,
            },
        ).status_code
        == 403
    )
    assert director.patch(path(team), json=override_data()).status_code == 403
    assert (
        director.post("/work/priorities/suggest", json=request(team)).status_code == 403
    )
    assert director.get("/director/unassessed").status_code == 403
    assert director.get("/admin/users").status_code == 403
    own = submit(director, fields(title="Собственное обращение директора")).json()
    assert (
        director.post(
            f"/appeals/{own['id']}/messages",
            json={"client_id": str(uuid4()), "body": "Дополнение к своему обращению"},
        ).status_code
        == 201
    )
    with Session(engine) as db:
        original = db.get(Appeal, appeal_id)
        company = Company(name="Другая компания директора")
        db.add(company)
        db.flush()
        alien = Appeal(
            **{
                **original.model_dump(),
                "id": None,
                "submission_id": uuid4(),
                "company_id": company.id,
            }
        )
        db.add(alien)
        db.commit()
        alien_id = alien.id
        company_id = str(company.id)
    assert director.get(f"/appeals/{alien_id}").status_code == 404
    assert director.get(f"/work/appeals/{alien_id}/priority").status_code == 404
    assert (
        director.get("/work/statistics", params={"company_id": company_id}).json()[
            "total"
        ]
        == 0
    )
    assert (
        director.get("/director/overview", params={"company_id": company_id}).json()[
            "items"
        ]
        == []
    )
    assert team["author"].get("/director/overview").status_code == 403
    assert team["first"].get(path(team)).status_code == 403


def test_coordinator_can_manage_four_roles_and_revocation_takes_effect(team, director):
    director_id = director.get("/auth/me").json()["id"]
    response = team["admin"].patch(
        "/admin/users/" + director_id,
        json={
            "roles": ["employee", "responsible", "coordinator", "director"],
            "is_active": True,
        },
    )
    assert response.status_code == 200 and len(response.json()["roles"]) == 4
    assert director.get("/admin/users").status_code == 200
    assert (
        team["admin"]
        .patch(
            "/admin/users/" + director_id,
            json={"roles": ["employee"], "is_active": True},
        )
        .status_code
        == 200
    )
    assert director.get("/director/overview").status_code == 403
    assert director.get("/work/statistics").status_code == 403
    assert director.get(f"/appeals/{team['appeal']['id']}").status_code == 404


def test_ai_override_refresh_restore_and_audit(team, monkeypatch):
    mock_advice(monkeypatch)
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json={**request(team), "consent": False})
        .status_code
        == 422
    )
    result = team["admin"].post("/work/priorities/suggest", json=request(team))
    assert result.status_code == 200, result.text
    item = result.json()[0]
    assert (
        item["version"] == 1
        and item["effective"]["level"] == "high"
        and not item["stale"]
    )
    assert team["admin"].patch(path(team), json=override_data(1)).status_code == 200
    refreshed = (
        team["admin"].post("/work/priorities/suggest", json=request(team, 2)).json()[0]
    )
    assert (
        refreshed["effective"]["source"] == "coordinator"
        and refreshed["effective"]["level"] == "low"
    )
    assert refreshed["ai"]["level"] == "high" and refreshed["version"] == 3
    assert (
        team["admin"].patch(path(team), json=override_data(1, level="high")).status_code
        == 409
    )
    assert team["admin"].patch(path(team), json=override_data(3)).json()["version"] == 3
    restored = (
        team["admin"].post(path(team) + "/use-ai", json={"expected_version": 3}).json()
    )
    assert (
        restored["version"] == 4
        and restored["effective"]["source"] == "openai"
        and restored["manual"] is None
    )
    assert {entry["action"] for entry in restored["history"]} == {
        "suggest",
        "override",
        "use_ai",
    }
    assert len(restored["history"]) == 4
    # The prioritization workflow never changes the employee's appeal lifecycle.
    assert (
        team["admin"].get(f"/appeals/{team['appeal']['id']}").json() == team["appeal"]
    )


def test_invalid_and_failed_model_responses_do_not_change_priorities(team, monkeypatch):
    mock_advice(monkeypatch)
    assert team["admin"].patch(path(team), json=override_data()).status_code == 200
    before = team["admin"].get(path(team)).json()

    def invalid(*args):
        return priorities.Recommendations(
            recommendations=[
                priorities.Recommendation(
                    appeal_id=999999,
                    lane="attention",
                    level="high",
                    reason="Неверная ссылка не должна менять приоритет.",
                    next_step="Проверить корректность ссылки на обращение.",
                )
            ]
        )

    monkeypatch.setattr(priorities.ai, "generate", invalid)
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json=request(team, 1))
        .status_code
        == 503
    )

    def outage(*args):
        raise HTTPException(503, "Сервис недоступен")

    monkeypatch.setattr(priorities.ai, "generate", outage)
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json=request(team, 1))
        .status_code
        == 503
    )
    assert team["admin"].get(path(team)).json() == before
    assert (
        team["admin"]
        .post(
            "/work/priorities/suggest",
            json={"appeals": request(team)["appeals"] * 2, "consent": True},
        )
        .status_code
        == 422
    )
    assert (
        team["admin"].patch(path(team), json=override_data(1, reason="  ")).status_code
        == 422
    )
    assert (
        team["admin"]
        .post(path(team) + "/use-ai", json={"expected_version": 1})
        .status_code
        == 409
    )


def test_batch_conflict_is_atomic_and_rechecks_coordinator_role(team, monkeypatch):
    second = submit(team["author"], fields(title="Второе обращение для оценки")).json()
    mock_advice(monkeypatch)
    original = priorities.ai.generate

    def conflicting(*args):
        result = original(*args)
        with Session(engine) as db:
            db.add(AppealPriority(appeal_id=team["appeal"]["id"], version=1))
            db.commit()
        return result

    monkeypatch.setattr(priorities.ai, "generate", conflicting)
    data = {
        "appeals": [
            {"appeal_id": team["appeal"]["id"], "expected_version": 0},
            {"appeal_id": second["id"], "expected_version": 0},
        ],
        "consent": True,
    }
    assert team["admin"].post("/work/priorities/suggest", json=data).status_code == 409
    with Session(engine) as db:
        assert db.get(AppealPriority, second["id"]) is None
        assert db.exec(select(PriorityEvent)).all() == []

    def revoke(*args):
        result = original(*args)
        with Session(engine) as db:
            actor = db.get(User, UUID(team["ids"]["admin_id"]))
            actor.roles = ["employee"]
            db.add(actor)
            db.commit()
        return result

    monkeypatch.setattr(priorities.ai, "generate", revoke)
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json=request(team, 1))
        .status_code
        == 403
    )


def test_stale_context_is_explained_and_promising_requires_idea(team, monkeypatch):
    mock_advice(monkeypatch)
    assert (
        team["admin"].post("/work/priorities/suggest", json=request(team)).status_code
        == 200
    )
    with Session(engine) as db:
        appeal = db.get(Appeal, team["appeal"]["id"])
        appeal.next_response_at = utcnow() - timedelta(hours=1)
        db.add(appeal)
        db.commit()
    item = team["admin"].get(path(team)).json()
    assert item["stale"] and item["overdue"]
    assert (
        team["admin"]
        .patch(path(team), json=override_data(1, lane="promising"))
        .status_code
        == 422
    )
    mock_advice(monkeypatch, lane="promising")
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json=request(team, 1))
        .status_code
        == 503
    )


def test_sorting_and_unassessed_queue_do_not_drop_ordinary_items(team, director):
    idea = submit(
        team["author"], fields(kind="idea", title="Проверить новый способ комплектации")
    ).json()
    assert (
        team["admin"]
        .patch(path(team), json=override_data(lane="attention", level="high"))
        .status_code
        == 200
    )
    assert (
        team["admin"]
        .patch(
            f"/work/appeals/{idea['id']}/priority",
            json=override_data(lane="promising", level="medium"),
        )
        .status_code
        == 200
    )
    board = director.get("/director/overview").json()
    assert board["counts"] == {"attention": 1, "promising": 1, "routine": 0}
    assert board["items"][0]["id"] == team["appeal"]["id"]
    assert (
        director.get("/director/overview?lane=promising").json()["items"][0]["id"]
        == idea["id"]
    )
    # Both manual evaluations can still get AI advice without losing the override.
    assert len(team["admin"].get("/director/unassessed").json()) == 2
    with Session(engine) as db:
        item = db.get(Appeal, idea["id"])
        item.status = "closed"
        db.add(item)
        db.commit()
    assert director.get("/director/overview?lane=promising").json()["total"] == 0
    assert (
        director.get("/director/overview?lane=promising&include_completed=true").json()[
            "total"
        ]
        == 1
    )


def test_director_demo_is_idempotent_and_separates_claims_from_evidence(setup):
    admin, _ = setup
    with Session(engine) as db:
        first = seed_director(db, PASSWORD)
        again = seed_director(db, PASSWORD)
        assert first == again and first["appeals"] == 27
        director = db.get(User, UUID(first["director_id"]))
        assert director.roles == ["employee", "director"] and password_hasher.verify(
            PASSWORD, director.password_hash
        )
    board = admin.get(
        "/director/overview",
        params={"company_id": first["company_id"], "lane": "routine"},
    ).json()
    claims = [
        item
        for item in board["items"]
        if "300" in item["title"] or "печенье" in item["title"]
    ]
    assert len(claims) == 2 and all(
        item["priority"]["effective"]["level"] == "low" for item in claims
    )
    assert all(item["priority"]["effective"]["source"] == "dataset" for item in claims)
    attention = admin.get(
        "/director/overview",
        params={"company_id": first["company_id"], "lane": "attention"},
    ).json()
    assert "Подозрение" in attention["items"][0]["title"]
    assert (
        "непроверенное подозрение"
        in attention["items"][0]["priority"]["effective"]["reason"]
    )
    assert (
        admin.get(
            "/work/statistics", params={"company_id": first["company_id"]}
        ).json()["total"]
        == 27
    )


def test_demo_mode_does_not_claim_to_be_ai_and_disabled_keeps_manual_choice(
    team, monkeypatch
):
    monkeypatch.setattr(settings, "ai_provider", "demo")
    response = team["admin"].post("/work/priorities/suggest", json=request(team))
    assert response.status_code == 200, response.text
    assert response.json()[0]["ai"]["source"] == "demo"
    monkeypatch.setattr(settings, "ai_provider", "disabled")
    assert team["admin"].patch(path(team), json=override_data(1)).status_code == 200
    assert (
        team["admin"]
        .post("/work/priorities/suggest", json=request(team, 2))
        .status_code
        == 503
    )
    assert team["admin"].get(path(team)).json()["effective"]["source"] == "coordinator"
