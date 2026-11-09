from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

from app.database import engine
from app.models import Appeal, Notification, User, utcnow
from app.notifications import scan_reminders
from sqlmodel import Session, select

from tests.test_discussion import act, send
from tests.test_feedback import ready, reply
from tests.test_work_queue import assign, assignment


def inbox(client):
    response = client.get("/notifications")
    assert response.status_code == 200, response.text
    return response.json()


def test_events_reading_and_isolation(team):
    assert inbox(team["author"])["items"][0]["kind"] == "received"
    assert inbox(team["admin"])["items"][0]["url"].startswith("/queue/")
    assert inbox(team["second"])["total"] == 0
    assert assign(team).status_code == 200
    own = inbox(team["author"])
    assert own["unread"] == 2
    item = own["items"][0]
    assert item["url"] == f"/appeals/{team['appeal']['id']}"
    assert team["second"].post(f"/notifications/{item['id']}/read").status_code == 404
    assert team["author"].post(f"/notifications/{item['id']}/read").status_code == 204
    assert team["author"].post(f"/notifications/{item['id']}/read").status_code == 204
    assert inbox(team["author"])["unread"] == 1
    assert team["author"].post("/notifications/read-all").status_code == 204
    assert inbox(team["author"])["unread"] == 0
    assert inbox(team["first"])["unread"] == 1
    assert team["author"].get("/notifications?page=0").status_code == 422
    team["author"].post("/auth/logout")
    assert team["author"].get("/notifications").status_code == 401


def test_message_retry_and_actor_exclusion(team):
    assert assign(team).status_code == 200
    key = str(uuid4())
    assert send(team, client_id=key).status_code == 201
    assert send(team, client_id=key).status_code == 200
    assert [x["kind"] for x in inbox(team["first"])["items"]].count("message") == 1
    assert all(x["kind"] != "message" for x in inbox(team["author"])["items"])
    assert act(team, "request_info", "Уточните расположение").status_code == 200
    assert inbox(team["author"])["items"][0]["kind"] == "request_info"
    assert send(team).status_code == 201
    assert act(team, "resolve", "Исправлено").status_code == 200
    assert inbox(team["author"])["items"][0]["kind"] == "resolve"


def test_old_assignee_loses_notification_access(team):
    assert assign(team).status_code == 200
    item = inbox(team["first"])["items"][0]
    assert (
        assign(
            team,
            assignment(
                team,
                responsible_id=team["second_id"],
                expected_version=1,
                reason="Передача",
            ),
        ).status_code
        == 200
    )
    assert inbox(team["first"])["total"] == 0
    assert team["first"].post(f"/notifications/{item['id']}/read").status_code == 404
    assert inbox(team["second"])["total"] == 1


def test_overdue_deduplication_concurrency_and_new_deadline(team):
    item = assign(team).json()
    now = utcnow() + timedelta(days=4)

    def scan():
        with Session(engine) as db:
            scan_reminders(db, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: scan(), range(2)))
    scan()
    for role in ["first", "admin"]:
        assert sum(x["kind"] == "overdue" for x in inbox(team[role])["items"]) == 1
    assert not any(x["kind"] == "overdue" for x in inbox(team["author"])["items"])
    assert (
        assign(
            team,
            assignment(
                team,
                expected_version=item["assignment_version"],
                next_response_at=(utcnow() + timedelta(days=3)).isoformat(),
                reason="Новый срок",
            ),
        ).status_code
        == 200
    )
    scan()
    assert sum(x["kind"] == "overdue" for x in inbox(team["first"])["items"]) == 2


def test_confirmation_reminder_and_closed_exclusion(team):
    item = ready(team)
    with Session(engine) as db:
        scan_reminders(db, utcnow() + timedelta(days=2))
    assert not any(
        x["kind"] == "confirmation_reminder" for x in inbox(team["author"])["items"]
    )
    with Session(engine) as db:
        scan_reminders(db, utcnow() + timedelta(days=4))
        scan_reminders(db, utcnow() + timedelta(days=5))
    assert (
        sum(
            x["kind"] == "confirmation_reminder" for x in inbox(team["author"])["items"]
        )
        == 1
    )
    assert reply(team, item).status_code == 200
    assert inbox(team["first"])["items"][0]["kind"] == "helped"
    with Session(engine) as db:
        before = len(db.exec(select(Notification)).all())
        scan_reminders(db, utcnow() + timedelta(days=20))
        assert len(db.exec(select(Notification)).all()) == before
        assert db.get(Appeal, item["id"]).status == "closed"


def test_inactive_responsible_not_notified_and_coordinator_fallback(team):
    assert assign(team).status_code == 200
    with Session(engine) as db:
        user = db.get(User, UUID(team["first_id"]))
        user.is_active = False
        db.add(user)
        db.commit()
        before = len(
            db.exec(select(Notification).where(Notification.user_id == user.id)).all()
        )
    assert send(team).status_code == 201
    with Session(engine) as db:
        scan_reminders(db, utcnow() + timedelta(days=4))
        assert (
            len(
                db.exec(
                    select(Notification).where(
                        Notification.user_id == UUID(team["first_id"])
                    )
                ).all()
            )
            == before
        )
    assert any(x["kind"] == "overdue" for x in inbox(team["admin"])["items"])
    assert any(x["kind"] == "message" for x in inbox(team["admin"])["items"])
