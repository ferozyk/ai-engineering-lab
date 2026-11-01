"""Typed errors raised by the banking service. Messages never contain session tokens."""


class BankingError(Exception):
    """Base class for banking service errors."""


class AuthenticationError(BankingError):
    """The caller could not be authenticated."""


class AuthorizationError(BankingError):
    """The authenticated principal may not access the requested resource."""


class NotFoundError(BankingError):
    """The requested resource does not exist."""


class InvalidRequestError(BankingError):
    """The request is malformed or semantically invalid."""
