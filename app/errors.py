"""Domain errors raised by services and mapped to HTTP codes in app.main."""


class NotFoundError(Exception):
    """A requested entity does not exist, or nothing matches within the requested bounds (404)."""


class InvalidRequestError(Exception):
    """Parameters are individually valid but make no sense together (400)."""
