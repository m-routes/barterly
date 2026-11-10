from unittest import mock

import psycopg
import pytest
from django.db import connection, connections
from django.db.backends.postgresql import base as pg_base
from django.test import override_settings

from apps.core.db.postgresql.base import DatabaseWrapper


def test_default_connection_uses_retrying_backend():
    assert isinstance(connections["default"], DatabaseWrapper)


@override_settings(DB_CONNECT_ATTEMPTS=3, DB_CONNECT_RETRY_DELAY=0)
def test_get_new_connection_retries_operational_errors():
    sentinel = object()
    with mock.patch.object(
        pg_base.DatabaseWrapper,
        "get_new_connection",
        side_effect=[psycopg.OperationalError("waking"), sentinel],
    ) as parent:
        assert connection.get_new_connection({"dbname": "x"}) is sentinel
    assert parent.call_count == 2


@override_settings(DB_CONNECT_ATTEMPTS=2, DB_CONNECT_RETRY_DELAY=0)
def test_get_new_connection_gives_up_after_configured_attempts():
    with (
        mock.patch.object(
            pg_base.DatabaseWrapper,
            "get_new_connection",
            side_effect=psycopg.OperationalError("down"),
        ) as parent,
        pytest.raises(psycopg.OperationalError),
    ):
        connection.get_new_connection({"dbname": "x"})
    assert parent.call_count == 2


@pytest.mark.django_db
def test_real_query_through_retrying_backend():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
