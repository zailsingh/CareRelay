from app.core.config import Settings


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
