from typing import Literal, Self

from pydantic import EmailStr, Field, HttpUrl, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    jwt_secret_key: str = Field(min_length=32)

    resend_api_key: str
    resend_from_email: EmailStr
    password_reset_frontend_url: HttpUrl
    password_reset_email_subject: str = Field(
        default="Mini Jira — Password Reset", min_length=1
    )

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

    @field_validator("password_reset_frontend_url")
    @classmethod
    def validate_reset_frontend_url(cls, url: HttpUrl) -> HttpUrl:
        if (
            url.username is not None
            or url.password is not None
            or url.query is not None
            or url.fragment is not None
            or (
                url.scheme != "https"
                and url.host not in {"localhost", "127.0.0.1", "[::1]"}
            )
        ):
            raise PydanticCustomError(
                "password_reset_url_invalid",
                "Password reset URL requires HTTPS outside localhost "
                "and must not contain credentials, query or fragment",
            )
        return url

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
