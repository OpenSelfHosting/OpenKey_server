from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Rejected in every environment — force operators to set a real secret.
_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change-me-to-a-long-random-secret",
        "dev-secret",
        "secret",
        "jwt-secret",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://openkey:openkey@localhost:5432/openkey"
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    # Short-lived access JWT; clients renew via refresh tokens.
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    # Comma-separated origins. Never use "*".
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )
    # Allow MV3 extension origins (chrome-extension:// / moz-extension://)
    # so the standalone browser vault can call the API without listing IDs.
    cors_allow_browser_extensions: bool = True
    # Sliding-window limits for unauthenticated auth endpoints (per client IP).
    auth_rate_limit_requests: int = 10
    auth_rate_limit_window_seconds: int = 60
    # When True, use the first X-Forwarded-For hop for rate-limit keys.
    # Only enable behind a reverse proxy that strips/overwrites that header.
    trust_proxy_headers: bool = False

    @field_validator("jwt_secret")
    @classmethod
    def reject_insecure_jwt_secret(cls, value: str) -> str:
        secret = value.strip()
        if secret.lower() in _INSECURE_JWT_SECRETS or secret in _INSECURE_JWT_SECRETS:
            raise ValueError(
                "JWT_SECRET is missing or uses a known insecure placeholder. "
                "Generate one with: openssl rand -hex 32"
            )
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return secret

    @field_validator("cors_origins")
    @classmethod
    def reject_insecure_cors(cls, value: str) -> str:
        origins = [o.strip() for o in value.split(",") if o.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must list at least one origin")
        if any(o == "*" for o in origins):
            raise ValueError("CORS_ORIGINS must not include '*'")
        return ",".join(origins)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """Chrome (a-p 32-char id) and Firefox (UUID) extension pages."""
        if not self.cors_allow_browser_extensions:
            return None
        return (
            r"^chrome-extension://[a-p]{32}$"
            r"|^moz-extension://[0-9a-fA-F]{8}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
