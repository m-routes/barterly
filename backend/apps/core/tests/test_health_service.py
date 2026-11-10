from unittest import mock

import pytest
from django.db import DatabaseError

from apps.core.services import health


@pytest.mark.django_db
def test_check_database_returns_true_when_db_reachable():
    assert health.check_database() is True


def test_check_database_returns_false_on_database_error():
    with mock.patch.object(health, "connections") as conns:
        conns.__getitem__.return_value.cursor.side_effect = DatabaseError("down")
        assert health.check_database() is False


def test_report_ok_and_dict():
    report = health.HealthReport(database=True)
    assert report.ok
    assert report.as_dict() == {"status": "ok", "database": "ok"}


def test_report_degraded_dict():
    report = health.HealthReport(database=False)
    assert not report.ok
    assert report.as_dict() == {"status": "degraded", "database": "unavailable"}
