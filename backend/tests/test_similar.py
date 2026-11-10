import pytest
from app.main import app
from fastapi.testclient import TestClient

from tests.helpers import HEADERS, PASSWORD, invite, token_from
from tests.test_appeals import fields, submit


@pytest.fixture()
def colleague(team):
    token = token_from(
        invite(team["admin"], team["ids"], email="colleague@example.com")
    )
    client = TestClient(app, headers=HEADERS)
    response = client.post("/auth/accept", json={"token": token, "password": PASSWORD})
    assert response.status_code == 201
    yield client
    client.close()


def search(client, title, description=""):
    response = client.post(
        "/similar", json={"title": title, "description": description}
    )
    assert response.status_code == 200, response.text
    return response.json()


def assign(team):
    appeal = team["appeal"]
    response = team["admin"].patch(
        f"/work/appeals/{appeal['id']}/assignment",
        json={
            "responsible_id": team["first_id"],
            "next_response_at": "2099-01-01T10:00:00+00:00",
            "expected_version": appeal["assignment_version"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_rephrased_problem_is_found_without_leaking_private_fields(team, colleague):
    matches = search(
        colleague,
        "На складе путают коробки",
        "При отгрузке путаем похожие коробки с камерами",
    )
    assert [item["id"] for item in matches] == [team["appeal"]["id"]]
    match = matches[0]
    assert match["relation"] == "other" and match["can_join"]
    assert match["score"] >= 0.18
    for private in ("description", "author", "author_id", "department"):
        assert private not in match


def test_unrelated_text_and_short_queries_find_nothing(team, colleague):
    assert search(colleague, "Не работает кондиционер в офисе продаж") == []
    assert search(colleague, "склад") == []


def test_author_sees_own_appeal_as_own(team):
    match = search(team["author"], "Путаются коробки на складе")[0]
    assert match["relation"] == "own" and not match["can_join"]


def test_join_notifies_and_shows_limited_card(team, colleague):
    appeal_id = team["appeal"]["id"]
    assign(team)
    joined = colleague.post(
        f"/appeals/{appeal_id}/support", json={"comment": "У нас в смене то же самое"}
    )
    assert joined.status_code == 200, joined.text
    card = joined.json()
    assert card["supporters"] == 1 and card["comment"] == "У нас в смене то же самое"
    assert "description" not in card and "author" not in card
    # Joining twice is idempotent.
    assert colleague.post(f"/appeals/{appeal_id}/support", json={}).json()[
        "supporters"
    ] == 1
    # The supporter still cannot open the private card or thread.
    assert colleague.get(f"/appeals/{appeal_id}").status_code == 404
    assert colleague.get(f"/appeals/{appeal_id}/messages").status_code == 404
    assert colleague.get(f"/appeals/{appeal_id}/support").status_code == 200
    assert [item["id"] for item in colleague.get("/supports").json()] == [appeal_id]
    assert search(colleague, "Путаются коробки на складе")[0]["relation"] == "supported"

    detail = team["first"].get(f"/appeals/{appeal_id}").json()
    assert detail["supporters"] == 1
    assert detail["supporters_list"][0]["comment"] == "У нас в смене то же самое"
    assert any("присоединился" in event["text"] for event in detail["history"])
    queue = team["admin"].get("/work/appeals").json()["items"]
    assert queue[0]["supporters"] == 1
    for client in (team["author"], team["first"]):
        kinds = [item["kind"] for item in client.get("/notifications").json()["items"]]
        assert "support" in kinds


def test_supporter_follows_official_progress_only(team, colleague):
    appeal_id = team["appeal"]["id"]
    appeal = assign(team)
    colleague.post(f"/appeals/{appeal_id}/support", json={})
    team["first"].post(
        f"/appeals/{appeal_id}/review",
        json={"action": "start", "expected_version": appeal["assignment_version"]},
    )
    team["first"].post(
        f"/appeals/{appeal_id}/messages",
        json={"client_id": "00000000-0000-4000-8000-000000000001", "body": "Вопрос"},
    )
    current = team["first"].get(f"/appeals/{appeal_id}").json()
    resolved = team["first"].post(
        f"/appeals/{appeal_id}/review",
        json={
            "action": "resolve",
            "expected_version": current["assignment_version"],
            "explanation": "Добавили цветную маркировку",
        },
    )
    assert resolved.status_code == 200, resolved.text
    kinds = {item["kind"] for item in colleague.get("/notifications").json()["items"]}
    assert {"start", "resolve"} <= kinds and "message" not in kinds
    card = colleague.get(f"/appeals/{appeal_id}/support").json()
    assert card["status"] == "awaiting_confirmation"
    assert card["result"] == "Добавили цветную маркировку"


def test_join_rules(team, colleague):
    appeal_id = team["appeal"]["id"]
    assert (
        team["author"].post(f"/appeals/{appeal_id}/support", json={}).status_code
        == 409
    )
    assert colleague.post("/appeals/999999/support", json={}).status_code == 404
    assert colleague.get(f"/appeals/{appeal_id}/support").status_code == 404
    # Other companies never see or join each other's appeals.
    other = team["admin"].post("/admin/companies", json={"name": "Другая компания"})
    company_id = other.json()["id"]
    department = team["admin"].post(
        "/admin/departments", json={"company_id": company_id, "name": "Офис"}
    ).json()
    token = token_from(
        invite(
            team["admin"],
            {"company_id": company_id, "department_id": department["id"]},
            email="outsider@example.com",
        )
    )
    outsider = TestClient(app, headers=HEADERS)
    outsider.post("/auth/accept", json={"token": token, "password": PASSWORD})
    assert search(outsider, "Путаются коробки на складе") == []
    assert outsider.post(f"/appeals/{appeal_id}/support", json={}).status_code == 404
    outsider.close()


def test_exclude_and_closed_appeals_cannot_be_joined(team, colleague):
    second = submit(
        team["author"],
        fields(title="Коробки камер путают при отгрузке со склада"),
    ).json()
    matches = search(colleague, "Путаются коробки на складе")
    assert {item["id"] for item in matches} == {team["appeal"]["id"], second["id"]}
    excluded = colleague.post(
        "/similar",
        json={"title": "Путаются коробки на складе", "exclude_id": second["id"]},
    ).json()
    assert [item["id"] for item in excluded] == [team["appeal"]["id"]]
