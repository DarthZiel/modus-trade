from app import ai
from app.config import settings
from app.database import engine
from app.models import Appeal
from pydantic import SecretStr
from sqlmodel import Session

from tests.test_appeals import fields, submit
from tests.test_work_queue import assign


def test_demo_suggestion_is_separate_and_no_extra_questions(team, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "demo")
    source = "На складе похожие коробки стоят без маркировки."
    response = team["author"].post(
        "/ai/appeal", json={"kind": "problem", "description": source}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "demo"
    suggestion = result["suggestion"]
    assert suggestion["description"] == source
    assert suggestion["category"] == "warehouse" and len(suggestion["questions"]) == 2
    response = team["author"].post(
        "/ai/appeal",
        json={
            "kind": "problem",
            "description": source,
            "answers": [
                {"question": suggestion["questions"][0], "answer": "На второй полке"}
            ],
        },
    )
    assert response.json()["suggestion"]["questions"] == []
    assert "На второй полке" in response.json()["suggestion"]["description"]
    with Session(engine) as db:
        assert db.get(Appeal, team["appeal"]["id"]).description != source


def test_unavailable_does_not_block_submission(team, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "disabled")
    assert (
        team["author"]
        .post(
            "/ai/appeal",
            json={"kind": "idea", "description": "Нужны подписи на коробках склада"},
        )
        .status_code
        == 503
    )
    assert submit(team["author"]).status_code == 201


def test_original_preserved_after_explicit_submission(team):
    original = "Нужны подписи на коробках склада"
    result = submit(
        team["author"],
        fields(
            description="Предлагаю маркировать полки и коробки на складе.",
            original_description=original,
        ),
    )
    assert result.status_code == 201, result.text
    assert result.json()["original_description"] == original
    assert result.json()["description"] != original


def test_ai_plan_requires_current_responsible_or_coordinator(team, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "demo")
    path = f"/ai/appeals/{team['appeal']['id']}/experiment"
    assert team["author"].post(path).status_code == 403
    assert team["second"].post(path).status_code == 404
    assert assign(team).status_code == 200
    result = team["first"].post(path)
    assert result.status_code == 200 and "baseline_plan" in result.json()["suggestion"]


def test_model_output_rejects_unsupported_numbers(team, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(
        ai,
        "generate",
        lambda *args: ai.Suggestion(
            title="Маркировка склада",
            description="На складе теряем 100000 рублей каждый месяц.",
            category="warehouse",
            questions=[],
        ),
    )
    assert (
        team["author"]
        .post(
            "/ai/appeal",
            json={
                "kind": "problem",
                "description": "На складе похожие коробки без маркировки",
            },
        )
        .status_code
        == 503
    )


def test_openai_contract_does_not_send_profile_or_store_response(team, monkeypatch):
    captured = {}
    proposal = ai.Suggestion(
        title="Подписи на складе",
        description="На складе похожие коробки без маркировки",
        category="warehouse",
        questions=[],
    )

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def parse(self, **kwargs):
            captured.update(kwargs)
            return type(
                "Result", (), {"status": "completed", "output_parsed": proposal}
            )()

    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("offline-test-only"))
    monkeypatch.setattr(ai, "OpenAI", FakeClient)
    response = team["author"].post(
        "/ai/appeal", json={"kind": "problem", "description": proposal.description}
    )
    assert response.status_code == 200
    assert captured["store"] is False
    assert "author@example.com" not in str(captured)
    assert "attachments" not in str(captured)
