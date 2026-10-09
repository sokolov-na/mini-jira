from typing import Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    cors_origins: list[str] = []
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None
    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        if any("*" in origin for origin in origins):
            raise ValueError("CORS origins must not contain wildcards")
        return origins

    @field_validator("refresh_cookie_domain")
    @classmethod
    def normalize_cookie_domain(cls, domain: str | None) -> str | None:
        return domain.strip() or None if domain is not None else None

    @model_validator(mode="after")
    def validate_cookie_security(self) -> Self:
        if (
            self.refresh_cookie_samesite == "none"
            and not self.refresh_cookie_secure
        ):
            raise ValueError("SameSite=none requires a Secure refresh cookie")
        return self


settings = Settings()  # pyright: ignore[reportCallIssue]
