"""Background work, behind a queue interface.

Code enqueues by name: `get_queue().enqueue("media.process", {"media_id": ...})`, with
an optional delay and task id (TASK_QUEUE_CLASS picks the queue):

- InlineTaskQueue (local and tests) runs the task straight away in the same request,
  logging failures. Delayed tasks are left to the job that looks for due work.
- CloudTasksQueue (deployed) creates an HTTP task aimed at POST /api/v1/tasks/<name>/,
  with an OIDC token for the tasks service account; that endpoint checks the token and
  calls run_task(name, payload). A task that raises gets a 503 and Cloud Tasks retries it
  with the queue's backoff (infra/terraform/modules/environment/tasks.tf).

Tasks must be idempotent, since Cloud Tasks delivers at least once.
"""

import contextlib
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
    def enqueue(
        self, name: str, payload: dict, *, delay_seconds: int = 0, task_id: str | None = None
    ) -> None: ...


class InlineTaskQueue:
    """Runs the task now. Failures are logged, not raised: the caller's work is done."""

    def enqueue(
        self, name: str, payload: dict, *, delay_seconds: int = 0, task_id: str | None = None
    ) -> None:
        if delay_seconds > 0:
            logger.info("Delayed task left for its job", extra={"task": name})
            return
        try:
            run_task(name, payload)
        except Exception:
            logger.exception("Task failed", extra={"task": name, "payload": payload})


@cache
def _build(path: str) -> TaskQueue:
    return import_string(path)()


def get_queue() -> TaskQueue:
    return _build(settings.TASK_QUEUE_CLASS)


class CloudTasksQueue:
    """Creates a Cloud Tasks HTTP task for POST {API_URL}/api/v1/tasks/<name>/."""

    def __init__(self) -> None:
        from google.cloud import tasks_v2

        self.client = tasks_v2.CloudTasksClient()
        self.parent = self.client.queue_path(
            settings.CLOUD_TASKS_PROJECT, settings.CLOUD_TASKS_LOCATION, settings.CLOUD_TASKS_QUEUE
        )

    def enqueue(
        self, name: str, payload: dict, *, delay_seconds: int = 0, task_id: str | None = None
    ) -> None:
        import datetime
        import json

        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2

        url = f"{settings.TASKS_AUDIENCE.rstrip('/')}/api/v1/tasks/{name}/"
        task: dict = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": settings.TASKS_INVOKER_EMAIL,
                    "audience": settings.TASKS_AUDIENCE,
                },
            }
        }
        if task_id:
            task["name"] = self.client.task_path(
                settings.CLOUD_TASKS_PROJECT,
                settings.CLOUD_TASKS_LOCATION,
                settings.CLOUD_TASKS_QUEUE,
                task_id,
            )
        if delay_seconds > 0:
            when = timestamp_pb2.Timestamp()
            when.FromDatetime(
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=delay_seconds)
            )
            task["schedule_time"] = when
        # The same task id queued already: nothing to do.
        with contextlib.suppress(AlreadyExists):
            self.client.create_task(parent=self.parent, task=task)
