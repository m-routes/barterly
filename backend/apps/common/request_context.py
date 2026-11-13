"""Per-request context (request id) carried through contextvars.

contextvars follow the request through sync and async code (asgiref copies the
context into sync_to_async threads), so logs and audit entries can read the id
without the request object.
"""

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str):
    """Set the id and return a token for reset_request_id()."""
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)
