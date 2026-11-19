"""The ledger: integer arithmetic, balanced idempotent posting, append-only rows."""

import importlib
from decimal import Decimal

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.money import ledger
from apps.money.ledger import (
    COMMISSION,
    ESCROW,
    GATEWAY,
    TALENT,
    LedgerError,
    Line,
    post,
    rupees_to_paise,
    share,
)
from apps.money.models import Account, LedgerEntry, LedgerTransaction

pytestmark = pytest.mark.django_db


class TestArithmetic:
    @pytest.mark.parametrize(
        ("amount", "bps", "expected"),
        [
            (1000, 800, 80),
            (5, 5000, 3),
            (1, 5000, 1),
            (1, 4999, 0),
            (500_000, 800, 40_000),
            (40_000, 1800, 7_200),
            (0, 800, 0),
            (12_345, 0, 0),
        ],
    )
    def test_share_rounds_half_up_in_integers(self, amount, bps, expected):
        assert share(amount, bps) == expected
        assert isinstance(share(amount, bps), int)

    @pytest.mark.parametrize("bad", [1.0, Decimal("1"), True, "100", None])
    def test_amounts_must_be_ints(self, bad):
        with pytest.raises(LedgerError):
            ledger.check_paise(bad)
        with pytest.raises(LedgerError):
            share(bad, 800)

    def test_shares_of_negatives_are_refused(self):
        with pytest.raises(LedgerError):
            share(-1, 800)

    @pytest.mark.parametrize(
        ("rupees", "paise"),
        [
            ("5000.00", 500_000),
            ("0.5", 50),
            ("1", 100),
            ("12345.67", 1_234_567),
            (Decimal("2.50"), 250),
        ],
    )
    def test_rupee_strings_convert_exactly(self, rupees, paise):
        assert rupees_to_paise(rupees) == paise

    @pytest.mark.parametrize("bad", ["1.005", "abc", 0.1])
    def test_bad_rupee_amounts_are_refused(self, bad):
        with pytest.raises(LedgerError):
            rupees_to_paise(bad)


class TestPosting:
    def test_a_movement_balances_and_posts_once(self):
        lines = [Line(GATEWAY, ESCROW, 1_000), Line(ESCROW, COMMISSION, 80)]
        first = post("test", "k1", lines, reference="pay_1")
        again = post("test", "k1", lines)
        assert first.pk == again.pk
        assert LedgerTransaction.objects.count() == 1
        entries = list(LedgerEntry.objects.order_by("line"))
        assert [(e.line, e.amount_paise, e.idempotency_key) for e in entries] == [
            (1, 1_000, "k1#1"),
            (2, 80, "k1#2"),
        ]
        assert ledger.balance(GATEWAY) == 1_000
        assert ledger.balance(ESCROW) == 920
        assert ledger.balance(COMMISSION) == 80
        assert ledger.is_balanced()

    def test_reusing_a_key_for_a_different_movement_is_an_error(self):
        post("test", "k2", [Line(GATEWAY, ESCROW, 1_000)])
        with pytest.raises(LedgerError, match="different movement"):
            post("test", "k2", [Line(GATEWAY, ESCROW, 999)])
        with pytest.raises(LedgerError, match="different movement"):
            post("other", "k2", [Line(GATEWAY, ESCROW, 1_000)])

    @pytest.mark.parametrize(
        "lines",
        [
            [],
            [Line(GATEWAY, ESCROW, 0)],
            [Line(GATEWAY, ESCROW, -5)],
            [Line(GATEWAY, GATEWAY, 5)],
            [Line(GATEWAY, "nope:account", 5)],
            [Line(GATEWAY, ESCROW, 5.0)],
        ],
    )
    def test_bad_lines_post_nothing(self, lines):
        with pytest.raises(LedgerError):
            post("test", "bad", lines)
        assert not LedgerTransaction.objects.exists()

    def test_a_failed_caller_rolls_its_movement_back(self):
        with pytest.raises(RuntimeError), transaction.atomic():
            post("test", "k3", [Line(GATEWAY, TALENT, 10)])
            raise RuntimeError
        assert not LedgerTransaction.objects.exists()

    def test_balances_can_be_read_per_booking_and_up_to_a_moment(self):
        from django.utils import timezone

        earlier = timezone.now() - timezone.timedelta(days=1)
        post("test", "old", [Line(GATEWAY, ESCROW, 300)], now=earlier)
        post("test", "new", [Line(GATEWAY, ESCROW, 200)])
        assert ledger.balance(ESCROW) == 500
        assert ledger.balance(ESCROW, until=earlier + timezone.timedelta(seconds=1)) == 300


class TestAppendOnly:
    def _raw(self, sql: str):
        with (
            pytest.raises(DatabaseError, match="append-only"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql)

    def test_the_database_refuses_updates_and_deletes(self):
        post("test", "k4", [Line(GATEWAY, ESCROW, 1_000)])
        self._raw("UPDATE money_ledgerentry SET amount_paise = 1")
        self._raw("DELETE FROM money_ledgerentry")
        self._raw("UPDATE money_ledgertransaction SET kind = 'x'")
        self._raw("DELETE FROM money_ledgertransaction")
        assert LedgerEntry.objects.get().amount_paise == 1_000

    def test_the_database_refuses_unbalanced_shapes(self):
        txn = post("test", "k5", [Line(GATEWAY, ESCROW, 1_000)])
        gateway = Account.objects.get(code=GATEWAY)
        with pytest.raises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(
                transaction=txn,
                line=2,
                debit_account=gateway,
                credit_account=gateway,
                amount_paise=5,
                idempotency_key="k5#2",
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(
                transaction=txn,
                line=3,
                debit_account=gateway,
                credit_account=Account.objects.get(code=ESCROW),
                amount_paise=0,
                idempotency_key="k5#3",
            )


def test_the_seeded_chart_of_accounts_matches_the_code():
    seed = importlib.import_module("apps.money.migrations.0003_seed_accounts")
    assert {
        code: (name, str(kind)) for code, (name, kind) in ledger.ACCOUNTS.items()
    } == seed.ACCOUNTS
    assert set(Account.objects.values_list("code", flat=True)) == set(ledger.ACCOUNTS)
