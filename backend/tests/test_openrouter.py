import json

import httpx
import pytest
from app import ai, openrouter
from app.config import settings
from openai import OpenAI as RealOpenAI
from pydantic import SecretStr

PROPOSAL = {
    "title": "Маркировка на складе",
    "description": "На складе похожие коробки без маркировки",
    "category": "warehouse",
    "questions": [],
}


@pytest.fixture()
def router_config(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("offline-router-key"))
    monkeypatch.setattr(settings, "openrouter_model", "vendor/arbitrary-model")
    monkeypatch.setattr(settings, "openrouter_experiment_model", "")
    monkeypatch.setattr(settings, "openrouter_output_mode", "schema")
    return monkeypatch


def transport(monkeypatch, *, content=None, finish="stop", refusal=None, code=200):
    captured = []

    def handle(request):
        captured.append(request)
        if code != 200:
            return httpx.Response(
                code,
                json={
                    "error": {
                        "message": "sensitive provider diagnostic",
                        "type": "invalid_request_error",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "mock-response",
                "object": "chat.completion",
                "created": 1,
                "model": "vendor/arbitrary-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(PROPOSAL)
                            if content is None
                            else content,
                            "refusal": refusal,
                        },
                    }
                ],
            },
        )

    def client(**kwargs):
        return RealOpenAI(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle))
        )

    monkeypatch.setattr(openrouter, "OpenAI", client)
    return captured


@pytest.mark.parametrize("mode", ["schema", "json", "prompt"])
def test_router_modes_use_configured_model_and_validate_output(router_config, mode):
    router_config.setattr(settings, "openrouter_output_mode", mode)
    captured = transport(router_config)
    result = ai.generate(
        ai.Suggestion, {"description": PROPOSAL["description"]}, "Редактор обращений"
    )
    assert result.description == PROPOSAL["description"]
    assert len(captured) == 1
    request = captured[0]
    data = json.loads(request.content)
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer offline-router-key"
    assert data["model"] == "vendor/arbitrary-model" and "models" not in data
    assert "attachments" not in str(data) and "author_id" not in str(data)
    if mode == "schema":
        assert data["response_format"]["json_schema"]["strict"]
        assert data["provider"]["require_parameters"]
    elif mode == "json":
        assert data["response_format"] == {"type": "json_object"}
    else:
        assert "response_format" not in data
    assert "JSON" in data["messages"][0]["content"]


def test_experiment_model_override_and_fallback(router_config):
    router_config.setattr(
        settings, "openrouter_experiment_model", "other/experiment-model"
    )
    payload = {
        "hypothesis": "Проверить маркировку",
        "change": "Подписать полки",
        "success_criterion": "Сравнить ошибки",
        "baseline_plan": "Записать исходные наблюдения",
    }
    captured = transport(router_config, content=json.dumps(payload))
    assert (
        ai.generate(ai.PlanSuggestion, {}, "План").hypothesis == payload["hypothesis"]
    )
    assert json.loads(captured[-1].content)["model"] == "other/experiment-model"
    router_config.setattr(settings, "openrouter_experiment_model", "")
    ai.generate(ai.PlanSuggestion, {}, "План")
    assert json.loads(captured[-1].content)["model"] == "vendor/arbitrary-model"


@pytest.mark.parametrize(
    "content,finish,refusal",
    [
        ("not JSON", "stop", None),
        (json.dumps({**PROPOSAL, "category": "invented"}), "stop", None),
        (json.dumps(PROPOSAL), "length", None),
        (json.dumps(PROPOSAL), "stop", "Refused"),
        ("{}", "stop", None),
    ],
)
def test_invalid_or_incomplete_response_is_safe_failure(
    router_config, content, finish, refusal
):
    transport(router_config, content=content, finish=finish, refusal=refusal)
    with pytest.raises(ai.HTTPException) as error:
        ai.generate(ai.Suggestion, {}, "Редактор")
    assert error.value.status_code == 503
    assert "sensitive" not in error.value.detail


@pytest.mark.parametrize("code", [400, 401, 402, 429, 500])
def test_provider_errors_are_not_retried_or_exposed(router_config, code):
    captured = transport(router_config, code=code)
    with pytest.raises(ai.HTTPException) as error:
        ai.generate(ai.Suggestion, {}, "Редактор")
    assert error.value.status_code == 503 and len(captured) == 1
    assert "sensitive" not in error.value.detail


def test_missing_model_cannot_send_request(router_config):
    router_config.setattr(settings, "openrouter_model", "")
    captured = transport(router_config)
    with pytest.raises(ai.HTTPException):
        ai.generate(ai.Suggestion, {}, "Редактор")
    assert captured == []


def test_status_and_api_responses_support_openrouter(team, router_config):
    transport(router_config)
    status = team["author"].get("/ai/status").json()
    assert status["available"] and status["mode"] == "openrouter"
    assert status["model"] == "vendor/arbitrary-model"
    assert "offline-router-key" not in str(status)
    response = team["author"].post(
        "/ai/appeal", json={"kind": "problem", "description": PROPOSAL["description"]}
    )
    assert response.status_code == 200 and response.json()["mode"] == "openrouter"
