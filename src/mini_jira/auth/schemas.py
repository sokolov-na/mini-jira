from pydantic import BaseModel


class UserCredentials(BaseModel):
    login: str
    password: str
