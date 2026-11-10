"""Retry opening a database connection while the database is briefly unavailable.

Cloud SQL restarts during maintenance, failover and tier changes, and new
connections fail for a few seconds meanwhile. Django opens connections lazily on
the first query of a request, so retrying here lets that query survive the restart
instead of returning a 500.
"""

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def connect_with_retry[T](
    connect: Callable[[], T],
    *,
    retry_on: tuple[type[BaseException], ...],
    attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `connect`, retrying on `retry_on` with exponential backoff.

    Delays are base_delay, 2*base_delay, ... capped at max_delay. The last error is
    re-raised once `attempts` calls have failed.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            return connect()
        except retry_on as exc:
            if attempt == attempts:
                logger.error("Database connection failed after %d attempts: %s", attempts, exc)
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Database connection attempt %d/%d failed (%s); retrying in %.2fs",
                attempt,
                attempts,
                exc,
                delay,
            )
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
