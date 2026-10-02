class UsernameAlreadyExists(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class UserNotFound(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class InvalidCredentials(Exception):
    pass
