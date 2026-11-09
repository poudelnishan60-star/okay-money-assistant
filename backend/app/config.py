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

    # LLM behaviour
    llm_reasoning_effort: str = "none"  # Qwen 3.8 on Groq: "none" = instruct mode (no thinking)
    llm_temperature: float = 0.6
    llm_max_tokens: int = 1024
    llm_timeout_seconds: float = 30.0
    chat_history_messages: int = 20
    chat_max_tool_rounds: int = 5

    # Public website: every visitor gets their own demo copy via POST /sessions.
    public_mode: bool = False  # true = requests without a session are refused
    session_ttl_days: int = 7
    max_sessions: int = 5000

    # Rate limits (per process; use Redis or similar if you run several backend instances)
    rate_chat_per_minute: int = 6  # per visitor
    rate_chat_per_day: int = 80  # per visitor
    rate_chat_global_per_hour: int = 300  # all visitors together, protects the Groq quota
    rate_sessions_per_ip_per_hour: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
