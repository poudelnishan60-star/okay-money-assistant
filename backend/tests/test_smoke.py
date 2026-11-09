from app.config import Settings


def test_health(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_openapi_contract_is_served(client) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert res.json()["info"]["title"] == "Khalti O-Kay AI Assistant API"


def test_default_llm_settings(monkeypatch) -> None:
    for var in ("LLM_MODEL", "LLM_FALLBACK_MODEL", "LLM_BASE_URL", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://api.groq.com/openai/v1"
    assert s.llm_model == "qwen/qwen3.8-27b"
    assert s.fallback_models == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert s.groq_api_key is None


def test_api_key_is_never_printed(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_value")
    s = Settings(_env_file=None)
    assert "gsk_secret_value" not in repr(s)
    assert s.groq_api_key is not None
    assert s.groq_api_key.get_secret_value() == "gsk_secret_value"
