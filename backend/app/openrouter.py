"""OpenRouter Chat Completions adapter; no provider or model fallback in the app."""

import json

from openai import OpenAI

from app.config import settings


class InvalidModelOutput(ValueError):
    pass


def generate(schema, payload: dict, instruction: str, *, experiment: bool = False):
    model = (
        settings.openrouter_experiment_model.strip() if experiment else ""
    ) or settings.openrouter_model.strip()
    mode = settings.openrouter_output_mode
    if not settings.openrouter_api_key.get_secret_value() or not model.strip():
        raise InvalidModelOutput("OpenRouter is not configured")
    schema_json = schema.model_json_schema()
    # JSON/prompt modes let models without JSON Schema support participate, but
    # application-side validation is identical in every mode.
    instruction += (
        "\nВерни только JSON-объект по схеме, без Markdown и пояснений:\n"
        + json.dumps(schema_json, ensure_ascii=False)
    )
    options = {}
    if mode == "schema":
        options["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema_json,
            },
        }
    elif mode == "json":
        options["response_format"] = {"type": "json_object"}
    if mode != "prompt":
        options["extra_body"] = {"provider": {"require_parameters": True}}
    with OpenAI(
        api_key=settings.openrouter_api_key.get_secret_value(),
        base_url="https://openrouter.ai/api/v1",
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    ) as client:
        result = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=settings.ai_max_output_tokens,
            **options,
        )
    if not result.choices or result.choices[0].finish_reason != "stop":
        raise InvalidModelOutput("Incomplete model response")
    message = result.choices[0].message
    if (
        not message
        or message.refusal
        or not isinstance(message.content, str)
        or not message.content
    ):
        raise InvalidModelOutput("No usable response")
    content = message.content.strip()
    if mode == "prompt" and content.startswith("```json\n") and content.endswith("```"):
        content = content[8:-3].strip()
    return schema.model_validate_json(content)
