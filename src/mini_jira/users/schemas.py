import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    email: EmailStr


class UserCreate(BaseModel):
    username: str = Field(min_length=3)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", v):
            raise ValueError(
                "Username must contain only Latin letters, digits, and hyphens"
                " (hyphen cannot be at start or end)"
            )
        return v.lower()

    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain a digit")
        return v


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
