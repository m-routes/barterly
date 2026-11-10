import pytest

from apps.core.services.db_retry import connect_with_retry


class Boom(Exception):
    pass


def failing(times: int, result="conn"):
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        if calls["n"] <= times:
            raise Boom(f"fail {calls['n']}")
        return result

    return connect, calls


def test_returns_immediately_on_success():
    sleeps: list[float] = []
    connect, calls = failing(0)
    assert connect_with_retry(connect, retry_on=(Boom,), sleep=sleeps.append) == "conn"
    assert calls["n"] == 1
    assert sleeps == []


def test_retries_with_exponential_backoff_then_succeeds():
    sleeps: list[float] = []
    connect, calls = failing(2)
    result = connect_with_retry(
        connect, retry_on=(Boom,), attempts=4, base_delay=0.5, sleep=sleeps.append
    )
    assert result == "conn"
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_backoff_is_capped():
    sleeps: list[float] = []
    connect, _ = failing(4)
    connect_with_retry(
        connect, retry_on=(Boom,), attempts=5, base_delay=1.0, max_delay=2.5, sleep=sleeps.append
    )
    assert sleeps == [1.0, 2.0, 2.5, 2.5]


def test_raises_last_error_after_all_attempts():
    sleeps: list[float] = []
    connect, calls = failing(10)
    with pytest.raises(Boom, match="fail 3"):
        connect_with_retry(connect, retry_on=(Boom,), attempts=3, sleep=sleeps.append)
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_other_errors_are_not_retried():
    def connect():
        raise ValueError("bad config")

    with pytest.raises(ValueError):
        connect_with_retry(connect, retry_on=(Boom,), sleep=lambda _: None)


def test_attempts_must_be_positive():
    with pytest.raises(ValueError, match="attempts"):
        connect_with_retry(lambda: "conn", retry_on=(Boom,), attempts=0)
