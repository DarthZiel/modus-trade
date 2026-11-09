from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from app.database import engine
from app.main import app
from app.models import Appeal, AppealEvent, utcnow
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.helpers import HEADERS, PASSWORD
from tests.test_appeals import fields, submit


def assignment(team, **overrides):
    return {
        "responsible_id": team["first_id"],
        "next_response_at": (utcnow() + timedelta(days=2)).isoformat(),
        "expected_version": 0,
        **overrides,
    }


def assign(team, data=None, client=None):
    return (client or team["admin"]).patch(
        f"/work/appeals/{team['appeal']['id']}/assignment",
        json=data or assignment(team),
    )


def test_assign_visibility_status_history(team):
    team["admin"].post("/auth/logout")
    # Re-login exercises normal cookie session rather than any fixture override.
    team["admin"].post(
        "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert team["first"].get("/work/appeals").json()["total"] == 0
    assert team["first"].get(f"/appeals/{team['appeal']['id']}").status_code == 404
    response = assign(team)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "reviewing" and item["assignment_version"] == 1
    assert item["responsible_id"] == team["first_id"] and item["responsible_available"]
    assert len(item["history"]) == 2
    assert (
        team["author"].get(f"/appeals/{item['id']}").json()["next_response_at"]
        == item["next_response_at"]
    )
    assert team["first"].get("/work/appeals").json()["total"] == 1
    assert team["first"].get(f"/appeals/{item['id']}").status_code == 200
    download = item["attachments"][0]["download_url"].removeprefix("/api")
    assert team["first"].get(download).status_code == 200
    assert team["second"].get(download).status_code == 404
    assert team["admin"].get("/appeals").json()["total"] == 0


def test_reassignment_and_deadline_require_reason(team):
    initial = assign(team).json()
    path = f"/appeals/{initial['id']}"
    data = assignment(team, responsible_id=team["second_id"], expected_version=1)
    assert assign(team, data).status_code == 422
    data["reason"] = "Передача специалисту по складу"
    result = assign(team, data)
    assert result.status_code == 200
    assert result.json()["assignment_version"] == 2
    assert "Передача специалисту по складу" in result.json()["history"][-1]["text"]
    assert team["first"].get(path).status_code == 404
    assert team["first"].get("/work/appeals").json()["total"] == 0
    assert team["second"].get(path).status_code == 200
    next_data = assignment(team, responsible_id=team["second_id"], expected_version=2)
    assert assign(team, next_data).status_code == 422
    next_data["reason"] = "Нужно время на проверку"
    assert assign(team, next_data).status_code == 200
    with Session(engine) as db:
        assert (
            len(
                db.exec(
                    select(AppealEvent).where(AppealEvent.appeal_id == initial["id"])
                ).all()
            )
            == 4
        )


def test_noop_and_stale_version(team):
    data = assignment(team)
    assert assign(team, data).status_code == 200
    assert assign(team, data).status_code == 409
    assert (
        assign(team, {**data, "expected_version": 1}).json()["assignment_version"] == 1
    )
    with Session(engine) as db:
        assert (
            len(
                db.exec(
                    select(AppealEvent).where(
                        AppealEvent.appeal_id == team["appeal"]["id"]
                    )
                ).all()
            )
            == 2
        )


def test_assignment_permissions_and_validation(team):
    assert assign(team, client=team["author"]).status_code == 403
    assert assign(team, client=team["first"]).status_code == 403
    assert team["author"].get("/work/appeals").status_code == 403
    assert team["first"].get("/work/responsibles").status_code == 403
    candidates = team["admin"].get("/work/responsibles").json()
    assert {item["id"] for item in candidates} == {team["first_id"], team["second_id"]}
    assert (
        assign(team, assignment(team, responsible_id=team["author_id"])).status_code
        == 422
    )
    assert (
        assign(team, assignment(team, responsible_id=str(uuid4()))).status_code == 422
    )
    assert (
        assign(
            team,
            assignment(
                team, next_response_at=(utcnow() - timedelta(seconds=1)).isoformat()
            ),
        ).status_code
        == 422
    )
    assert (
        assign(team, assignment(team, next_response_at="2026-12-31T12:00")).status_code
        == 422
    )
    assert assign(team, assignment(team, expected_version=-1)).status_code == 422
    assert assign(team, assignment(team, reason="x" * 1001)).status_code == 422
    assert (
        team["admin"]
        .patch("/work/appeals/999999/assignment", json=assignment(team))
        .status_code
        == 404
    )


def test_disabled_and_role_revoked_responsibles(team):
    result = assign(team).json()
    assert (
        team["admin"]
        .patch(
            "/admin/users/" + team["first_id"],
            json={"roles": ["responsible"], "is_active": False},
        )
        .status_code
        == 200
    )
    assert (
        not team["author"]
        .get(f"/appeals/{result['id']}")
        .json()["responsible_available"]
    )
    assert team["first"].get("/work/appeals").status_code == 401
    assert (
        assign(
            team, assignment(team, expected_version=1, reason="Новый срок")
        ).status_code
        == 422
    )
    assert team["first_id"] not in {
        item["id"] for item in team["admin"].get("/work/responsibles").json()
    }
    # Another active responsible loses work access immediately after role removal.
    assert (
        team["admin"]
        .patch(
            "/admin/users/" + team["second_id"],
            json={"roles": ["employee"], "is_active": True},
        )
        .status_code
        == 200
    )
    assert team["second"].get("/work/appeals").status_code == 403


def test_queue_filters_and_search(team):
    first = team["appeal"]
    submit(team["author"], fields(kind="idea", title="Маркировка 100% коробок")).json()
    assert team["admin"].get("/work/appeals?filter=unassigned").json()["total"] == 2
    assign(team)
    assert team["admin"].get("/work/appeals?filter=unassigned").json()["total"] == 1
    assert team["admin"].get("/work/appeals?kind=idea").json()["total"] == 1
    assert team["admin"].get("/work/appeals?status=reviewing").json()["total"] == 1
    assert (
        team["admin"]
        .get("/work/appeals?responsible_id=" + team["first_id"])
        .json()["total"]
        == 1
    )
    assert (
        team["admin"]
        .get("/work/appeals?company_id=" + team["ids"]["company_id"])
        .json()["total"]
        == 2
    )
    assert (
        team["admin"].get("/work/appeals?department_id=" + str(uuid4())).json()["total"]
        == 0
    )
    assert (
        team["admin"]
        .get("/work/appeals", params={"q": first["number"]})
        .json()["items"][0]["id"]
        == first["id"]
    )
    assert team["admin"].get("/work/appeals", params={"q": "100%"}).json()["total"] == 1
    assert team["admin"].get("/work/appeals", params={"q": "_"}).json()["total"] == 0
    assert (
        team["admin"].get("/work/appeals", params={"q": "Сотрудник"}).json()["total"]
        == 2
    )
    assert (
        team["first"]
        .get("/work/appeals?responsible_id=" + team["second_id"])
        .json()["total"]
        == 0
    )
    assert team["first"].get("/work/appeals?filter=unassigned").json()["total"] == 0
    with Session(engine) as db:
        appeal = db.get(Appeal, first["id"])
        appeal.next_response_at = utcnow() - timedelta(hours=1)
        db.add(appeal)
        db.commit()
    overdue = team["admin"].get("/work/appeals?filter=overdue").json()
    assert overdue["total"] == 1 and overdue["items"][0]["is_overdue"]
    with Session(engine) as db:
        appeal = db.get(Appeal, first["id"])
        appeal.status = "closed"
        db.add(appeal)
        db.commit()
    assert team["admin"].get("/work/appeals?filter=overdue").json()["total"] == 0
    assert (
        assign(team, assignment(team, expected_version=1, reason="Смена")).status_code
        == 409
    )
    assert team["admin"].get("/work/appeals?page_size=1").json()["total"] == 2
    assert (
        team["admin"].get("/work/appeals?page=2&page_size=1").json()["items"][0]["id"]
        == first["id"]
    )


def test_concurrent_coordinators_do_not_overwrite(team):
    cookies = dict(team["admin"].cookies)

    def update(responsible_id):
        with TestClient(app, headers=HEADERS, cookies=cookies) as client:
            return assign(
                team, assignment(team, responsible_id=responsible_id), client
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, [team["first_id"], team["second_id"]])) == [
            200,
            409,
        ]
    item = team["admin"].get(f"/appeals/{team['appeal']['id']}").json()
    assert item["assignment_version"] == 1 and len(item["history"]) == 2
