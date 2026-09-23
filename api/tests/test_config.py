import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.ai_provider import MockAIProvider, OpenRouterAIProvider, build_ai_provider


def test_comma_separated_cors_origins_are_supported(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8081, https://app.example.com")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:8081", "https://app.example.com"]


def test_production_rejects_default_secret() -> None:
    try:
        Settings(app_env="production", jwt_secret="short", _env_file=None)
    except ValueError as error:
        assert "JWT_SECRET" in str(error)
    else:
        raise AssertionError("Expected production secret validation to fail")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ai_provider": "unknown"}, "AI_PROVIDER"),
        ({"ai_model": "   "}, "AI_MODEL"),
        ({"ai_provider": "openrouter", "ai_model": "vendor/model"}, "OPENROUTER_API_KEY"),
        (
            {
                "ai_provider": "openrouter",
                "openrouter_api_key": "secret",
                "ai_model": "mock-care-relay-v1",
            },
            "explicit OpenRouter model ID",
        ),
        ({"ai_max_tool_calls": 0}, "AI_MAX_TOOL_CALLS"),
    ],
)
def test_invalid_ai_configuration_fails_clearly(overrides, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **overrides)


def test_provider_factory_uses_explicit_configuration() -> None:
    mock = build_ai_provider(Settings(_env_file=None))
    openrouter = build_ai_provider(
        Settings(
            _env_file=None,
            ai_provider="openrouter",
            openrouter_api_key="server-only-secret",
            ai_model="openai/gpt-5-mini",
        )
    )
    assert isinstance(mock, MockAIProvider)
    assert mock.model == "mock-care-relay-v1"
    assert isinstance(openrouter, OpenRouterAIProvider)
    assert openrouter.model == "openai/gpt-5-mini"
