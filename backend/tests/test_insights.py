from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import similarities
from app.config import settings
from app.database import engine
from app.hackathon_demo import seed_dataset
from app.main import app
from app.models import Appeal, AppealFeedback, AppealRelation, Company, utcnow
from tests.helpers import HEADERS, PASSWORD
from tests.test_appeals import fields, submit
from tests.test_work_queue import assign


def search_path(team):
    return f"/work/appeals/{team['appeal']['id']}/similarities/search"


def suggestion(other, kind="same_problem"):
    return similarities.Matches(
        matches=[
            similarities.Match(
                appeal_id=other["id"],
                kind=kind,
                topic="Единая маркировка оборудования",
                reason="Оба сотрудника описывают отсутствие маркировки одних и тех же коробок.",
            )
        ]
    )


def prepare(team, monkeypatch, kind="same_problem"):
    other = submit(
        team["author"],
        fields(
            title="Нужна маркировка коробок",
            description="На складе не подписаны похожие коробки оборудования.",
        ),
    ).json()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(
        similarities.ai, "generate", lambda *args: suggestion(other, kind)
    )
    result = team["admin"].post(search_path(team), json={"consent": True})
    assert result.status_code == 200, result.text
    return other, result.json()["items"][0]


def test_proposals_require_coordinator_consent_and_do_not_change_appeals(
    team, monkeypatch
):
    for client in [team["author"], team["first"]]:
        assert client.post(search_path(team), json={"consent": True}).status_code == 403
        assert (
            client.get(f"/work/appeals/{team['appeal']['id']}/similarities").status_code
            == 403
        )
        assert client.get("/work/topics").status_code == 403
        assert client.get("/work/statistics").status_code == 403
    monkeypatch.setattr(settings, "ai_provider", "openai")
    assert team["admin"].post(search_path(team), json={}).status_code == 422
    _, relation = prepare(team, monkeypatch)
    assert relation["status"] == "pending"
    assert team["admin"].get("/work/topics").json() == []
    path = f"/work/similarities/{relation['id']}"
    assert (
        team["author"]
        .patch(path, json={"status": "confirmed", "expected_version": 0})
        .status_code
        == 403
    )
    result = team["admin"].patch(
        path, json={"status": "confirmed", "expected_version": 0}
    )
    assert result.json()["reviewer"] == "Координатор"
    assert len(team["admin"].get("/work/topics").json()) == 1
    assert (
        team["admin"].get(f"/appeals/{team['appeal']['id']}").json() == team["appeal"]
    )
    # The relation is a single undirected pair; repeat searches/confirmations do not duplicate it.
    assert (
        team["admin"]
        .post(search_path(team), json={"consent": True})
        .json()["considered"]
        == 0
    )
    assert (
        team["admin"]
        .patch(path, json={"status": "confirmed", "expected_version": 0})
        .status_code
        == 200
    )
    with Session(engine) as db:
        assert len(db.exec(select(AppealRelation)).all()) == 1


def test_review_reclassification_staleness_and_dismissal(team, monkeypatch):
    _, relation = prepare(team, monkeypatch, "related_topic")
    path = f"/work/similarities/{relation['id']}"
    assert (
        team["admin"]
        .patch(path, json={"status": "confirmed", "expected_version": 0})
        .status_code
        == 200
    )
    assert team["admin"].get("/work/topics").json() == []
    assert (
        team["admin"]
        .patch(
            path,
            json={"status": "confirmed", "kind": "same_problem", "expected_version": 0},
        )
        .status_code
        == 409
    )
    assert (
        team["admin"]
        .patch(
            path,
            json={"status": "confirmed", "kind": "same_problem", "expected_version": 1},
        )
        .status_code
        == 200
    )
    assert len(team["admin"].get("/work/topics").json()) == 1
    assert (
        team["admin"]
        .patch(path, json={"status": "dismissed", "expected_version": 2})
        .status_code
        == 200
    )
    assert team["admin"].get("/work/topics").json() == []
    assert (
        team["admin"]
        .post(search_path(team), json={"consent": True})
        .json()["considered"]
        == 0
    )


def test_ai_payload_scope_validation_and_failure_preserves_confirmed_links(
    team, monkeypatch
):
    _, relation = prepare(team, monkeypatch)
    assert (
        team["admin"]
        .patch(
            f"/work/similarities/{relation['id']}",
            json={"status": "confirmed", "expected_version": 0},
        )
        .status_code
        == 200
    )
    candidate = submit(
        team["author"], fields(title="Другая заявка без маркировки")
    ).json()
    with Session(engine) as db:
        other_company = Company(name="Другая компания")
        db.add(other_company)
        db.flush()
        appeal = Appeal(
            **{
                **db.get(Appeal, candidate["id"]).model_dump(),
                "id": None,
                "submission_id": uuid4(),
                "company_id": other_company.id,
                "title": "Не передавать модели",
            }
        )
        db.add(appeal)
        db.commit()
        alien_id = appeal.id
    captured = {}

    def invalid(schema, payload, instruction):
        captured.update(payload)
        assert "данными" in instruction
        return suggestion({"id": alien_id})

    monkeypatch.setattr(similarities.ai, "generate", invalid)
    response = team["admin"].post(search_path(team), json={"consent": True})
    assert response.status_code == 503
    assert all(item["id"] != alien_id for item in captured["candidates"])
    assert "author@example.com" not in str(captured) and "attachments" not in str(
        captured
    )
    monkeypatch.setattr(settings, "ai_provider", "disabled")
    assert (
        team["admin"].post(search_path(team), json={"consent": True}).status_code == 503
    )
    assert len(team["admin"].get("/work/topics").json()) == 1


def test_parallel_searches_store_one_pair(team, monkeypatch):
    other = submit(team["author"], fields(title="Подписать похожие коробки")).json()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(similarities.ai, "generate", lambda *args: suggestion(other))
    cookies = dict(team["admin"].cookies)

    def run(_):
        with TestClient(app, headers=HEADERS, cookies=cookies) as client:
            return client.post(search_path(team), json={"consent": True}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, range(2))) == [200, 200]
    with Session(engine) as db:
        assert len(db.exec(select(AppealRelation)).all()) == 1


def test_first_response_ignores_assignment_author_and_start_and_survives_reopen(team):
    item = assign(team).json()
    path = f"/appeals/{item['id']}"
    for client in [team["author"]]:
        assert (
            client.post(
                path + "/messages",
                json={"client_id": str(uuid4()), "body": "Дополнение автора"},
            ).status_code
            == 201
        )
    current = team["first"].get(path).json()
    assert (
        team["first"]
        .post(
            path + "/review",
            json={"action": "start", "expected_version": current["assignment_version"]},
        )
        .status_code
        == 200
    )
    stats = team["admin"].get("/work/statistics").json()
    assert stats["unanswered"] == 1 and stats["average_first_response_hours"] is None
    current = team["first"].get(path).json()
    assert (
        team["first"]
        .post(
            path + "/review",
            json={
                "action": "request_info",
                "explanation": "На какой полке нет маркировки?",
                "expected_version": current["assignment_version"],
            },
        )
        .status_code
        == 200
    )
    with Session(engine) as db:
        first = db.get(Appeal, item["id"]).first_response_at
        assert first is not None
    assert (
        team["author"]
        .post(
            path + "/messages",
            json={"client_id": str(uuid4()), "body": "На второй полке склада"},
        )
        .status_code
        == 201
    )
    current = team["first"].get(path).json()
    result = (
        team["first"]
        .post(
            path + "/review",
            json={
                "action": "resolve",
                "explanation": "Полка промаркирована",
                "expected_version": current["assignment_version"],
            },
        )
        .json()
    )
    assert (
        team["author"]
        .post(
            path + "/feedback",
            json={
                "client_id": str(uuid4()),
                "outcome": "reopen",
                "comment": "Маркировка всё ещё мелкая",
                "expected_version": result["assignment_version"],
            },
        )
        .status_code
        == 200
    )
    with Session(engine) as db:
        assert db.get(Appeal, item["id"]).first_response_at == first
    stats = team["admin"].get("/work/statistics").json()
    assert stats["answered"] == 1 and stats["reopened"] == 1 and stats["confirmed"] == 0


def test_statistics_cohort_timezone_missing_values_filters_and_real_confirmation(team):
    now = utcnow()
    boundary = now.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )
    with Session(engine) as db:
        first = db.get(Appeal, team["appeal"]["id"])
        first.created_at = boundary
        first.first_response_at = boundary + timedelta(hours=3)
        first.next_response_at = now - timedelta(hours=1)
        first.status = "in_progress"
        db.add(first)
        db.commit()
    second = submit(team["author"], fields(title="Отклонённое обращение")).json()
    third = submit(team["author"], fields(title="Подтверждённое решение")).json()
    fourth = submit(team["author"], fields(title="Закрыто без подтверждения")).json()
    with Session(engine) as db:
        for entry, status in [
            (second, "rejected"),
            (third, "closed"),
            (fourth, "closed"),
        ]:
            item = db.get(Appeal, entry["id"])
            item.created_at = boundary
            item.first_response_at = boundary + timedelta(hours=1)
            item.status = status
            db.add(item)
        db.add(
            AppealFeedback(
                appeal_id=third["id"],
                author_id=team["author_id"],
                client_id=uuid4(),
                outcome="helped",
                comment="Помогло",
                result_snapshot="Выполнено",
                created_at=boundary + timedelta(hours=4),
            )
        )
        db.commit()
    local_date = (boundary + timedelta(hours=5)).date().isoformat()
    params = {"date_from": local_date, "date_to": local_date, "utc_offset_minutes": 300}
    stats = team["admin"].get("/work/statistics", params=params).json()
    assert stats["total"] == 4 and stats["average_first_response_hours"] == 1.5
    assert stats["confirmed"] == 1 and stats["confirmed_percent"] == 25
    assert stats["rejected"] == 1 and stats["overdue"] == 1
    assert stats["trend"][0]["received"] == 4 and stats["trend"][0]["confirmed"] == 1
    assert (
        team["admin"]
        .get("/work/statistics", params={**params, "utc_offset_minutes": 0})
        .json()["total"]
        == 0
    )
    assert (
        team["admin"]
        .get("/work/statistics", params={**params, "department_id": str(uuid4())})
        .json()["total"]
        == 0
    )
    assert (
        team["admin"]
        .get("/work/statistics?date_from=2020-01-01&date_to=2026-01-01")
        .status_code
        == 422
    )
    assert (
        team["admin"]
        .get("/work/statistics?date_from=2026-01-02&date_to=2026-01-01")
        .status_code
        == 422
    )


def test_dataset_is_isolated_idempotent_and_ready_for_statistics(setup):
    admin, _ = setup
    with Session(engine) as db:
        first = seed_dataset(db, PASSWORD)
        again = seed_dataset(db, PASSWORD)
        assert (
            first["created"]
            and not again["created"]
            and first["appeals"] == again["appeals"] == 24
        )
    stats = admin.get(
        "/work/statistics", params={"company_id": first["company_id"]}
    ).json()
    assert stats["total"] == 24 and stats["confirmed"] == 1 and stats["reopened"] == 1
    assert stats["unanswered"] > 0 and stats["average_first_response_hours"] > 0
    assert len(stats["topics"]) == 1 and stats["topics"][0]["authors"] == 2
    with Session(engine) as db:
        assert all(
            "Синтетический пример" in item.description
            for item in db.exec(
                select(Appeal).where(Appeal.company_id == first["company_id"])
            ).all()
        )


def test_search_is_bounded_and_rejects_duplicate_model_references(team, monkeypatch):
    with Session(engine) as db:
        original = db.get(Appeal, team["appeal"]["id"])
        for n in range(45):
            db.add(
                Appeal(
                    **{
                        **original.model_dump(),
                        "id": None,
                        "submission_id": uuid4(),
                        "title": f"Маркировка коробок — вариант {n}",
                    }
                )
            )
        db.commit()
    monkeypatch.setattr(settings, "ai_provider", "openai")

    def empty(schema, payload, instruction):
        assert len(payload["candidates"]) == similarities.CANDIDATE_LIMIT
        assert all(len(item["description"]) <= 1200 for item in payload["candidates"])
        return similarities.Matches(matches=[])

    monkeypatch.setattr(similarities.ai, "generate", empty)
    result = team["admin"].post(search_path(team), json={"consent": True}).json()
    assert result["considered"] == 40 and result["available"] == 45

    def duplicate(schema, payload, instruction):
        value = suggestion(payload["candidates"][0]).matches[0]
        return similarities.Matches(matches=[value, value])

    monkeypatch.setattr(similarities.ai, "generate", duplicate)
    assert (
        team["admin"].post(search_path(team), json={"consent": True}).status_code == 503
    )
    with Session(engine) as db:
        assert db.exec(select(AppealRelation)).all() == []


def test_legacy_migration_backfills_human_evidence_without_losing_appeals(team):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    appeal_id = team["appeal"]["id"]
    assert assign(team).status_code == 200
    assert (
        team["first"]
        .post(
            f"/appeals/{appeal_id}/messages",
            json={
                "client_id": str(uuid4()),
                "body": "Проверим маркировку второй полки",
            },
        )
        .status_code
        == 201
    )
    with Session(engine) as db:
        original = db.get(Appeal, appeal_id)
        created_at = original.created_at
        title = original.title
    command.downgrade(Config("alembic.ini"), "cf001")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT title FROM appeals WHERE id=:id"), {"id": appeal_id}
            ).scalar_one()
            == title
        )
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine) as db:
        restored = db.get(Appeal, appeal_id)
        assert (
            restored.first_response_at is not None
            and restored.first_response_at >= created_at
        )
        assert restored.title == title
