from psycopg import Error
from sqlalchemy.exc import IntegrityError

from mini_jira.exceptions import EmailAlreadyExists, UsernameAlreadyExists


def handle_integrity_error(exc: IntegrityError) -> None:
    if not isinstance(exc.orig, Error):
        raise exc

    constraint = exc.orig.diag.constraint_name

    if constraint == "users_username_key":
        raise UsernameAlreadyExists from exc

    if constraint == "users_email_key":
        raise EmailAlreadyExists from exc

    raise exc
