"""Align user column lengths with ORM and API validation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c2b4f7d1a60"
down_revision: str | Sequence[str] | None = "e0ee6d6e0e26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE users IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM users
                WHERE char_length(username) > 32 OR char_length(email) > 256
            ) THEN
                RAISE EXCEPTION
                    'Cannot constrain users: oversized username or email';
            END IF;
        END $$;
        """
    )
    op.alter_column(
        "users",
        "username",
        existing_type=sa.String(),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(),
        type_=sa.String(256),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(256),
        type_=sa.String(),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "username",
        existing_type=sa.String(32),
        type_=sa.String(),
        existing_nullable=False,
    )
