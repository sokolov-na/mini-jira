# Migrations

Run Alembic from `api` using the intended `DATABASE_URL` from
[application settings](configuration.md):

```powershell
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
uv run alembic check
```

Verify the target connection and back up existing data before applying changes.
Do not rewrite applied revisions. Add a new revision for schema changes, review
its upgrade/downgrade operations, and test both fresh installation and upgrade
from the previous revision in the [dedicated test database](testing.md).

```powershell
uv run alembic revision --autogenerate -m "describe schema change"
uv run pytest tests/integration/test_migrations.py -ra
```

Autogenerate is a starting point: inspect generated SQL and data conversions.
`alembic check` can miss differences involving unspecified varchar lengths;
explicit schema checks complement it. Downgrades may be destructive and must
be reviewed before use.

## Length limits and existing data

Before applying username/email length limits to an existing database, check:

```sql
SELECT
    count(*) FILTER (WHERE char_length(username) > 32) AS oversized_usernames,
    count(*) FILTER (WHERE char_length(email) > 256) AS oversized_emails
FROM users;
```

If either count is nonzero, stop and resolve the records explicitly. Do not
truncate values or delete users automatically. The length-limit migration locks
`users`, checks the data, and aborts transactionally on oversized values.
Schedule it with allowance for an exclusive table lock until commit.
