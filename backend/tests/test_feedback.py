from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.main import app
from fastapi.testclient import TestClient

from tests.helpers import HEADERS
from tests.test_discussion import act, send
from tests.test_work_queue import assign


def ready(team):
    assert assign(team).status_code == 200
    result = act(team, "resolve", "Полки промаркированы")
    assert result.status_code == 200
    return result.json()


def reply(team, item, outcome="helped", comment="", client=None, key=None):
    return (client or team["author"]).post(
        f"/appeals/{item['id']}/feedback",
        json={
            "client_id": key or str(uuid4()),
            "outcome": outcome,
            "comment": comment,
            "expected_version": item["assignment_version"],
        },
    )


def test_author_confirms_result_and_closes(team):
    item = ready(team)
    result = reply(team, item, comment="Проверил: ошибки устранены")
    assert result.status_code == 200, result.text
    closed = result.json()
    assert closed["status"] == "closed" and closed["result"] == "Полки промаркированы"
    assert closed["feedback"][0]["outcome"] == "helped"
    assert closed["feedback"][0]["comment"] == "Проверил: ошибки устранены"
    assert closed["feedback"][0]["result_snapshot"] == "Полки промаркированы"
    assert closed["feedback"][0]["created_at"]
    assert "Автор подтвердил результат" in closed["history"][-1]["text"]
    assert team["author"].get("/appeals?filter=completed").json()["total"] == 1
    assert team["author"].get("/appeals?filter=active").json()["total"] == 0
    assert send(team, body="Спасибо").json()["appeal"]["status"] == "closed"
    assert reply(team, closed, outcome="reopen", comment="Повтор").status_code == 409


def test_only_author_can_confirm_or_return(team):
    item = ready(team)
    assert reply(team, item, client=team["admin"]).status_code == 403
    assert reply(team, item, client=team["first"]).status_code == 403
    assert reply(team, item, client=team["second"]).status_code == 404
    assert (
        team["author"].get(f"/appeals/{item['id']}").json()["status"]
        == "awaiting_confirmation"
    )


def test_return_preserves_previous_result_and_adds_message(team):
    item = ready(team)
    assert reply(team, item, "reopen", "   ").status_code == 422
    result = reply(team, item, "reopen", "Коробки всё ещё путают на второй полке")
    assert result.status_code == 200, result.text
    reopened = result.json()
    assert (
        reopened["status"] == "in_progress"
        and reopened["responsible_id"] == team["first_id"]
    )
    assert (
        reopened["result"] is None
        and reopened["decision"] is None
        and reopened["decided_at"] is None
    )
    assert reopened["next_response_at"] is None
    assert reopened["feedback"][0]["result_snapshot"] == "Полки промаркированы"
    page = team["first"].get(f"/appeals/{item['id']}/messages").json()
    assert len(page["items"]) == 1 and page["items"][0]["kind"] == "feedback_return"
    assert page["items"][0]["body"] == "Коробки всё ещё путают на второй полке"
    assert (
        act(
            team,
            "resolve",
            "Дополнительно промаркирована вторая полка",
            client=team["first"],
        ).status_code
        == 200
    )
    latest = team["author"].get(f"/appeals/{item['id']}").json()
    assert reply(team, latest).json()["status"] == "closed"
    receipts = team["author"].get(f"/appeals/{item['id']}").json()["feedback"]
    assert len(receipts) == 2
    assert (
        receipts[-1]["result_snapshot"] == "Дополнительно промаркирована вторая полка"
    )


def test_unavailable_responsible_returns_to_coordinator(team):
    item = ready(team)
    team["admin"].patch(
        "/admin/users/" + team["first_id"],
        json={"roles": ["responsible"], "is_active": False},
    )
    response = reply(team, item, "reopen", "Результат не помог")
    assert response.status_code == 200
    returned = response.json()
    assert returned["status"] == "received" and returned["responsible_id"] is None
    assert team["admin"].get("/work/appeals?filter=unassigned").json()["total"] == 1
    assert "нового ответственного" in returned["history"][-1]["text"]


def test_removed_responsible_role_returns_to_coordinator(team):
    item = ready(team)
    team["admin"].patch(
        "/admin/users/" + team["first_id"],
        json={"roles": ["employee"], "is_active": True},
    )
    returned = reply(team, item, "reopen", "Нужна доработка").json()
    assert returned["status"] == "received" and returned["responsible_id"] is None
    assert team["first"].get(f"/appeals/{item['id']}").status_code == 404


def test_retry_and_old_return_do_not_repeat_action(team):
    item = ready(team)
    key = str(uuid4())
    first = reply(team, item, "reopen", "Нужна доработка", key=key)
    repeat = reply(team, item, "reopen", "Нужна доработка", key=key)
    assert first.status_code == repeat.status_code == 200
    assert first.json() == repeat.json()
    assert reply(team, item, "helped", key=key).status_code == 409
    assert (
        len(team["author"].get(f"/appeals/{item['id']}/messages").json()["items"]) == 1
    )
    assert act(team, "resolve", "Исправлено повторно").status_code == 200
    retried = reply(team, item, "reopen", "Нужна доработка", key=key)
    assert retried.json()["status"] == "awaiting_confirmation"
    assert len(retried.json()["feedback"]) == 1


def test_validation_and_stale_version(team):
    item = team["appeal"]
    assert reply(team, item).status_code == 409
    item = ready(team)
    assert reply(team, item, "unknown").status_code == 422
    assert reply(team, item, comment="x" * 10001).status_code == 422
    assert send(team, body="Есть дополнительный вопрос").status_code == 201
    assert reply(team, item).status_code == 409
    assert team["author"].get(f"/appeals/{item['id']}").json()["feedback"] == []


def test_simultaneous_help_and_return_single_winner(team):
    item = ready(team)
    cookies = dict(team["author"].cookies)

    def decide(outcome):
        with TestClient(app, headers=HEADERS, cookies=cookies) as client:
            return reply(team, item, outcome, "Комментарий автора", client).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, ["helped", "reopen"])) == [200, 409]
    result = team["author"].get(f"/appeals/{item['id']}").json()
    assert (
        result["status"] in {"closed", "in_progress"} and len(result["feedback"]) == 1
    )
