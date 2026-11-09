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
    # Comma-separated, tried in order on 429 / retired model. (llama-3.3-70b-versatile from
    # the original spec is no longer offered on Groq.)
    llm_fallback_model: str = "openai/gpt-oss-120b,openai/gpt-oss-20b"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'khalti_ai.db').as_posix()}"
    cors_origins: str = ""  # extra exact origins, comma-separated
    # Dev default: any localhost / 127.0.0.1 port (Flutter web picks a random port).
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    # Prototype convenience: seed the demo data on startup if the database has no users.
    auto_seed: bool = True

    # LLM behaviour
    llm_reasoning_effort: str = "none"  # Qwen 3.8 on Groq: "none" = instruct mode (no thinking)
    llm_gpt_oss_reasoning_effort: str = "low"  # gpt-oss fallbacks: low = fast, few tokens
    llm_temperature: float = 0.6
    llm_max_tokens: int = 500  # answers are short; Groq free tier is 8,000 tokens/min
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
    rate_chat_global_per_minute: int = 6  # all visitors together: Groq free tier is
    # 8,000 tokens/min per model (~2-3 questions/min each; 3 models with fallback)
    rate_chat_global_per_hour: int = 300
    rate_sessions_per_ip_per_hour: int = 10

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_model.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
