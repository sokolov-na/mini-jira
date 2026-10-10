from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    jwt_secret_key: str = Field(min_length=32)

    cors_origins: list[str] = []

    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal[
        "lax",
        "strict",
        "none",
    ] = "lax"
    refresh_cookie_domain: str | None = None

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"
    log_format: Literal[
        "json",
        "console",
    ] = "console"

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        if any("*" in origin for origin in origins):
            raise PydanticCustomError(
                "cors_origin_wildcard",
                "CORS origins must not contain wildcards",
            )
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
            raise PydanticCustomError(
                "refresh_cookie_secure_required",
                "SameSite=none requires a Secure refresh cookie",
            )
        return self


settings = Settings()  # pyright: ignore[reportCallIssue]
