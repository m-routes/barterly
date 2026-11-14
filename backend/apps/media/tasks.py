"""Background work, behind a queue interface.

Code enqueues by name: `get_queue().enqueue("media.process", {"media_id": ...})`.
InlineTaskQueue (the current setting) runs the task straight away in the same request.
Moving to Cloud Tasks means a CloudTasksQueue whose enqueue() creates an HTTP task
aimed at an internal endpoint that verifies the task's OIDC token and calls
run_task(name, payload); task functions don't change. Tasks must be idempotent, since
Cloud Tasks retries.
"""

import logging
from collections.abc import Callable
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

TaskFn = Callable[[dict], None]
_REGISTRY: dict[str, TaskFn] = {}


def task(name: str) -> Callable[[TaskFn], TaskFn]:
    def register(fn: TaskFn) -> TaskFn:
        _REGISTRY[name] = fn
        return fn

    return register


def run_task(name: str, payload: dict) -> None:
    try:
        fn = _REGISTRY[name]
    except KeyError:
        raise LookupError(f"No task named {name!r}") from None
    fn(payload)


class TaskQueue(Protocol):
    def enqueue(self, name: str, payload: dict) -> None: ...


class InlineTaskQueue:
    """Runs the task now. Failures are logged, not raised: the caller's work is done."""

    def enqueue(self, name: str, payload: dict) -> None:
        try:
            run_task(name, payload)
        except Exception:
            logger.exception("Task failed", extra={"task": name, "payload": payload})


@cache
def _build(path: str) -> TaskQueue:
    return import_string(path)()


def get_queue() -> TaskQueue:
    return _build(settings.TASK_QUEUE_CLASS)
