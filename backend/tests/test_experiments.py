from datetime import timedelta
from uuid import uuid4

from app.database import engine
from app.models import Appeal, Experiment, Notification, utcnow
from app.notifications import scan_reminders
from sqlmodel import Session, select

from tests.test_discussion import act
from tests.test_work_queue import assign, assignment


def plan(team, **overrides):
    item = team["admin"].get(f"/appeals/{team['appeal']['id']}").json()
    return {
        "client_id": str(uuid4()),
        "expected_version": item["assignment_version"],
        "hypothesis": "Маркировка уменьшит путаницу",
        "change": "Подписать одну полку на складе",
        "success_criterion": "Сравнить число ошибок за одинаковое время",
        "starts_at": utcnow().isoformat(),
        "ends_at": (utcnow() + timedelta(days=7)).isoformat(),
        **overrides,
    }


def create(team, data=None, client=None):
    return (client or team["first"]).post(
        f"/appeals/{team['appeal']['id']}/experiments", json=data or plan(team)
    )


def finish(team, item, **overrides):
    return team["first"].post(
        f"/appeals/{team['appeal']['id']}/experiments/{item['id']}/finish",
        json={
            "expected_version": item["version"],
            "actions": "Полки подписаны и проверены",
            "observations": "Автор сообщил, что коробки проще различать",
            "outcome": "expand",
            **overrides,
        },
    )


def test_experiment_lifecycle_requires_author_confirmation(team):
    assert assign(team).status_code == 200
    data = plan(team)
    response = create(team, data)
    assert response.status_code == 201, response.text
    item = response.json()
    assert create(team, data).json()["id"] == item["id"]
    assert create(team).status_code == 409
    assert act(team, "resolve", "Маркировка завершена").status_code == 409
    result = finish(team, item)
    assert result.status_code == 200, result.text
    completed = result.json()
    assert not completed["quantitative_evidence"] and completed["delta"] is None
    assert finish(team, item).status_code == 200
    assert (
        finish(team, item, observations="Противоположные наблюдения").status_code == 409
    )
    assert (
        team["author"].get(f"/appeals/{team['appeal']['id']}").json()["status"]
        == "in_progress"
    )
    path = f"/appeals/{team['appeal']['id']}/experiments/{item['id']}/comment"
    assert (
        team["first"]
        .post(
            path,
            json={
                "comment": "Я сам решил за автора",
                "expected_version": completed["version"],
            },
        )
        .status_code
        == 403
    )
    assert (
        team["author"]
        .post(
            path,
            json={
                "comment": "Проверил, теперь коробки не путаю",
                "expected_version": completed["version"],
            },
        )
        .status_code
        == 200
    )
    assert (
        act(team, "resolve", "Маркировка завершена, результат проверен").status_code
        == 200
    )
    with Session(engine) as db:
        assert db.get(Appeal, team["appeal"]["id"]).status == "awaiting_confirmation"


def test_paired_measurements_and_zero_baseline(team):
    assert assign(team).status_code == 200
    item = create(
        team, plan(team, metric="Ошибки", unit="случаев за смену", before_value=0)
    ).json()
    result = finish(team, item, after_value=2)
    assert result.status_code == 200
    assert result.json()["quantitative_evidence"] and result.json()["delta"] == 2


def test_rights_and_input_validation(team):
    assert create(team, client=team["author"]).status_code == 403
    assert create(team, client=team["second"]).status_code == 404
    assert create(team, client=team["admin"]).status_code == 409
    assert assign(team).status_code == 200
    assert create(team, plan(team, before_value=10)).status_code == 422
    assert (
        create(
            team, plan(team, ends_at=(utcnow() - timedelta(days=1)).isoformat())
        ).status_code
        == 422
    )
    assert create(team, plan(team, expected_version=0)).status_code == 409
    assert (
        create(
            team, plan(team, before_value="NaN", metric="Ошибки", unit="шт")
        ).status_code
        == 422
    )
    item = create(team).json()
    assert finish(team, item, after_value=4).status_code == 422


def test_overdue_reminder_deduplication_and_reassignment(team):
    assert assign(team).status_code == 200
    item = create(team).json()
    with Session(engine) as db:
        scan_reminders(db, utcnow() + timedelta(days=8))
        scan_reminders(db, utcnow() + timedelta(days=9))
        notices = db.exec(
            select(Notification).where(Notification.kind == "experiment_overdue")
        ).all()
        assert len(notices) == 2  # coordinator and responsible
    current = team["admin"].get(f"/appeals/{team['appeal']['id']}").json()
    assert (
        assign(
            team,
            assignment(
                team,
                responsible_id=team["second_id"],
                expected_version=current["assignment_version"],
                reason="Передача эксперимента специалисту",
            ),
        ).status_code
        == 200
    )
    with Session(engine) as db:
        experiment = db.exec(select(Experiment)).one()
        assert str(experiment.responsible_id) == team["second_id"]
        assert experiment.version == item["version"] + 1
    assert (
        team["first"].get(f"/appeals/{team['appeal']['id']}/experiments").status_code
        == 404
    )


def test_overview_obeys_roles(team):
    assert team["author"].get("/work/overview").status_code == 403
    assert team["admin"].get("/work/overview").json()["unassigned"] == 1
    assert team["second"].get("/work/overview").json()["unassigned"] == 0
    assert assign(team).status_code == 200
    assert create(team).status_code == 201
    assert team["admin"].get("/work/overview").json()["active_experiments"] == 1
    assert team["first"].get("/work/overview").json()["active_experiments"] == 1
    assert team["second"].get("/work/overview").json()["active_experiments"] == 0
