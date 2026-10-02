from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="refresh_tokens",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    username: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(256),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
