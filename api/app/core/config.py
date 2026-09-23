from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareRelay API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://carerelay:carerelay@localhost:5432/carerelay"
    jwt_secret: str = "local-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    ai_provider: str = "mock"
    openrouter_api_key: str = ""
    ai_model: str = "mock-care-relay-v1"
    ai_max_tool_calls: int = 4
    apple_client_id: str = ""
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    email_provider: str = "mock"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    invite_base_url: str = "carerelay://invite"
    invite_expire_hours: int = 168
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8081",
        "http://localhost:19006",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.app_env.lower() == "production" and (
            len(self.jwt_secret) < 32 or self.jwt_secret == "local-development-secret-change-me"
        ):
            raise ValueError("JWT_SECRET must be a unique value of at least 32 characters")
        if self.ai_provider not in {"mock", "openrouter"}:
            raise ValueError("AI_PROVIDER must be mock or openrouter")
        if not self.ai_model.strip():
            raise ValueError("AI_MODEL must be an explicit model ID")
        if self.ai_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for the OpenRouter provider")
        if self.ai_provider == "openrouter" and self.ai_model == "mock-care-relay-v1":
            raise ValueError("AI_MODEL must be an explicit OpenRouter model ID")
        if not 1 <= self.ai_max_tool_calls <= 10:
            raise ValueError("AI_MAX_TOOL_CALLS must be between 1 and 10")
        if self.email_provider not in {"mock", "gmail"}:
            raise ValueError("EMAIL_PROVIDER must be mock or gmail")
        if self.email_provider == "gmail":
            missing = [
                name
                for name, value in (
                    ("SMTP_USERNAME", self.smtp_username),
                    ("SMTP_PASSWORD", self.smtp_password),
                    ("EMAIL_FROM", self.email_from),
                    ("SMTP_HOST", self.smtp_host),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Gmail email provider requires {', '.join(missing)}")
            if not self.smtp_use_tls:
                raise ValueError("Gmail email provider requires SMTP_USE_TLS=true")
            if not 1 <= self.smtp_port <= 65535:
                raise ValueError("SMTP_PORT must be between 1 and 65535")
        if not self.invite_base_url.strip():
            raise ValueError("INVITE_BASE_URL must not be empty")
        if not 1 <= self.invite_expire_hours <= 24 * 30:
            raise ValueError("INVITE_EXPIRE_HOURS must be between 1 and 720")
        if self.app_env.lower() == "production" and not self.apple_client_id:
            raise ValueError("APPLE_CLIENT_ID is required in production")
        if self.app_env.lower() == "production" and not self.apple_jwks_url:
            raise ValueError("APPLE_JWKS_URL is required in production")
        return self

    @property
    def dev_login_enabled(self) -> bool:
        return self.app_env.lower() in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
