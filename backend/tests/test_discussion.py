from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from app.database import engine
from app.main import app
from app.models import AppealMessage
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.helpers import HEADERS
from tests.test_work_queue import assign


def send(team, client=None, **data):
    return (client or team["author"]).post(
        f"/appeals/{team['appeal']['id']}/messages",
        json={
            "client_id": str(uuid4()),
            "body": "Дополнительные сведения об обращении",
            **data,
        },
    )


def act(team, action, explanation="", version=None, client=None):
    client = client or team["admin"]
    if version is None:
        version = client.get(f"/appeals/{team['appeal']['id']}").json()[
            "assignment_version"
        ]
    return client.post(
        f"/appeals/{team['appeal']['id']}/review",
        json={
            "action": action,
            "explanation": explanation,
            "expected_version": version,
        },
    )


def test_messages_permissions_and_validation(team):
    path = f"/appeals/{team['appeal']['id']}/messages"
    first = send(team)
    assert first.status_code == 201, first.text
    assert first.json()["message"]["sender_id"] == team["author_id"]
    assert first.json()["message"]["is_author"]
    assert team["second"].get(path).status_code == 404
    assert send(team, team["second"]).status_code == 404
    assign_result = assign(
        team,
        {
            "responsible_id": team["first_id"],
            "next_response_at": "2099-01-01T12:00:00Z",
            "expected_version": 1,
        },
    )
    assert assign_result.status_code == 200
    assert send(team, team["first"], body="Проверим комплектование").status_code == 201
    rows = team["author"].get(path).json()["items"]
    assert len(rows) == 2 and rows[0]["id"] < rows[1]["id"]
    assert send(team, body="   ").status_code == 422
    assert send(team, body="x" * 10001).status_code == 422
    assert send(team, sender_id=team["first_id"]).status_code == 422


def test_question_and_author_reply_restore_in_progress(team):
    assign(team)
    assert act(team, "start", client=team["first"]).json()["status"] == "in_progress"
    result = act(team, "request_info", "Какие модели путаются?", client=team["first"])
    assert result.status_code == 200 and result.json()["status"] == "needs_info"
    page = team["author"].get(f"/appeals/{team['appeal']['id']}/messages").json()
    assert page["items"][0]["kind"] == "question"
    assert team["author"].get("/appeals?filter=needs_reply").json()["total"] == 1
    assert (
        send(team, team["admin"], body="Ждём уточнения").json()["appeal"]["status"]
        == "needs_info"
    )
    answer = send(team, body="Модели A и B, фото были в исходном обращении")
    assert answer.json()["appeal"]["status"] == "in_progress"
    assert team["author"].get("/appeals?filter=needs_reply").json()["total"] == 0
    assert "Автор ответил" in answer.json()["appeal"]["history"][-1]["text"]


def test_question_restores_reviewing_and_forbids_early_decision(team):
    assert act(team, "start", version=0).status_code == 409
    assign(team)
    assert act(team, "request_info", "Уточните место").json()["status"] == "needs_info"
    assert act(team, "resolve", "Готово").status_code == 409
    assert send(team).json()["appeal"]["status"] == "reviewing"
    assert act(team, "resolve", "   ").status_code == 422
    assert act(team, "start", client=team["author"]).status_code == 403


def test_result_waits_for_author_confirmation(team):
    assign(team)
    result = act(
        team,
        "resolve",
        "Полки промаркированы, проведена проверка комплектования",
        client=team["first"],
    )
    assert result.status_code == 200, result.text
    item = result.json()
    assert item["status"] == "awaiting_confirmation" and item["decision"] == "Выполнено"
    assert item["next_response_at"] is None and not item["is_overdue"]
    assert item["decided_at"] and "Полки промаркированы" in item["result"]
    assert (
        team["author"].get(f"/appeals/{item['id']}").json()["result"] == item["result"]
    )
    assert (
        send(team, body="Спасибо, проверю завтра").json()["appeal"]["status"]
        == "awaiting_confirmation"
    )
    assert act(team, "reject", "Передумали").status_code == 409
    assert act(team, "resolve", "Подтверждаю", client=team["author"]).status_code == 403


def test_rejection_explained_and_discussion_remains_available(team):
    assign(team)
    assert act(team, "reject").status_code == 422
    result = act(team, "reject", "Изменение несовместимо с текущим оборудованием")
    assert result.status_code == 200
    assert (
        result.json()["status"] == "rejected"
        and result.json()["decision"] == "Отклонено"
    )
    assert result.json()["result"] == "Изменение несовместимо с текущим оборудованием"
    assert result.json()["next_response_at"] is None
    assert (
        send(team, body="Можно ли рассмотреть другой вариант?").json()["appeal"][
            "status"
        ]
        == "rejected"
    )


def test_duplicate_messages_and_stale_decisions(team):
    assign(team)
    initial = (
        team["admin"]
        .get(f"/appeals/{team['appeal']['id']}")
        .json()["assignment_version"]
    )
    key = str(uuid4())
    first = send(team, client_id=key)
    second = send(team, client_id=key)
    assert first.json()["message"]["id"] == second.json()["message"]["id"]
    assert (
        first.json()["appeal"]["assignment_version"]
        == second.json()["appeal"]["assignment_version"]
    )
    assert send(team, client_id=key, body="Другой текст").status_code == 409
    assert act(team, "resolve", "Результат", version=initial).status_code == 409
    assert (
        len(
            team["author"]
            .get(f"/appeals/{team['appeal']['id']}/messages")
            .json()["items"]
        )
        == 1
    )


def test_message_pagination_and_reassignment_permissions(team):
    assign(team)
    with Session(engine) as db:
        for index in range(60):
            db.add(
                AppealMessage(
                    appeal_id=team["appeal"]["id"],
                    sender_id=UUID(team["author_id"]),
                    client_id=uuid4(),
                    body=f"Сообщение {index}",
                )
            )
        db.commit()
    path = f"/appeals/{team['appeal']['id']}/messages"
    latest = team["author"].get(path).json()
    assert latest["has_more"] and len(latest["items"]) == 50
    older = (
        team["author"].get(path, params={"before_id": latest["items"][0]["id"]}).json()
    )
    assert not older["has_more"] and len(older["items"]) == 10
    assert older["items"][-1]["id"] < latest["items"][0]["id"]
    assert (
        assign(
            team,
            {
                "responsible_id": team["second_id"],
                "next_response_at": "2099-01-01T12:00:00Z",
                "expected_version": 1,
                "reason": "Передача специалисту",
            },
        ).status_code
        == 200
    )
    assert team["first"].get(path).status_code == 404
    assert send(team, team["first"]).status_code == 404
    assert team["second"].get(path).status_code == 200


def test_concurrent_decisions_have_single_winner(team):
    assign(team)
    cookies = dict(team["admin"].cookies)

    def decide(action):
        with TestClient(app, headers=HEADERS, cookies=cookies) as client:
            return act(
                team, action, "Обоснование решения", version=1, client=client
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, ["resolve", "reject"])) == [200, 409]
    item = team["admin"].get(f"/appeals/{team['appeal']['id']}").json()
    assert item["assignment_version"] == 2 and len(item["history"]) == 3
