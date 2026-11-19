import pytest

from apps.money.tests.helpers import ensure_accounts


@pytest.fixture(autouse=True)
def _chart_of_accounts(db):
    ensure_accounts()
