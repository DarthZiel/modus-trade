from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")
    ai_provider: Literal["disabled", "demo", "openai", "openrouter"] = "disabled"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""
    openrouter_experiment_model: str = ""
    openrouter_output_mode: Literal["schema", "json", "prompt"] = "schema"
    # Speech-to-text for Telegram voice messages (model must accept input_audio).
    openrouter_audio_model: str = "google/gemini-2.5-flash"
    ai_timeout_seconds: float = Field(default=20, ge=1, le=120)
    ai_max_output_tokens: int = Field(default=2500, ge=256, le=16384)
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    bot_token: SecretStr = SecretStr("")
    bot_api_secret: SecretStr = SecretStr("")
    bot_username: str = ""
    mini_app_url: str = ""
    upload_dir: Path = Path("./uploads")
    cookie_secure: bool = False
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "modus"
    db_password: str = "modus_local"
    db_name: str = "modus"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()
