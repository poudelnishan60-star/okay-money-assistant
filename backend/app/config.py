"""Settings loaded from environment / backend/.env. Secrets live only here, never in the app."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend, wherever you start from


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "qwen/qwen3.8-27b"
    llm_fallback_model: str = "llama-3.3-70b-versatile"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'khalti_ai.db').as_posix()}"
    cors_origins: str = ""  # extra exact origins, comma-separated
    # Dev default: any localhost / 127.0.0.1 port (Flutter web picks a random port).
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    # Prototype convenience: seed the demo data on startup if the database has no users.
    auto_seed: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
