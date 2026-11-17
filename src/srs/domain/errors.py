class InvalidRequest(Exception):
    """The request is well-formed but asks for something invalid (unknown id, missing field for the kind, etc)."""


class NotFound(Exception):
    pass
