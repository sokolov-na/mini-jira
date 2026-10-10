import re
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
)
from pydantic_core import PydanticCustomError


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    email: EmailStr


def validate_username(username: str) -> str:
    if not re.fullmatch(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", username):
        raise PydanticCustomError(
            "username_invalid",
            "Username must contain only Latin letters, digits, and hyphens"
            " (hyphen cannot be at start or end)",
        )
    return username.lower()


_email_adapter = TypeAdapter[str](EmailStr)


def normalize_email(email: str) -> str:
    return _email_adapter.validate_python(email)


Username = Annotated[
    str,
    Field(min_length=3, max_length=32),
    AfterValidator(validate_username),
]

Password = Annotated[str, Field(min_length=8)]


class UserCredentials(BaseModel):
    login: str
    password: Password


class UserRegister(BaseModel):
    username: Username
    email: EmailStr
    password: Password


class UserUpdate(BaseModel):
    username: Username | None = None
    email: EmailStr | None = None
