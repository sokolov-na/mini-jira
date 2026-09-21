from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(32),
        unique=True,
    )
    email: Mapped[str] = mapped_column(
        String(256),
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String,
    )
