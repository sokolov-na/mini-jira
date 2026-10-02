from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    email: EmailStr


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
