class UsernameAlreadyExists(Exception):
    """The username is already assigned to another user."""


class EmailAlreadyExists(Exception):
    """The email address is already assigned to another user."""


class UserNotFound(Exception):
    """The requested user does not exist."""


class InvalidTokenError(Exception):
    """The authentication token is missing or invalid."""


class InvalidCredentials(Exception):
    """The supplied login credentials could not be authenticated."""
