"""
Tests for ShiftVarianceReport -- cross-cashier shift shortage/overage
oversight (#459). Covers the acceptance criteria: generation with a mix
of balanced/short/over shifts, the cashier filter, and registration.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.core.reports.definitions.shift_variance_report import ShiftVarianceReport

_counter = 0


@pytest.fixture
def two_cashiers(db_session):
    """Create two cashiers, each with one closed shift: one short, one over."""
    global _counter
    _counter += 1
    suffix = str(_counter)

    permission = Permission(code=f"variance_report_test_{suffix}")
    role = Role(name=f"VarianceRole_{suffix}", permissions=[permission])
    db_session.add_all([permission, role])
    db_session.flush()

    short_cashier = User(username=f"short_cashier_{suffix}", pin_hash="hash", role=role)
    over_cashier = User(username=f"over_cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([short_cashier, over_cashier])
    db_session.flush()

    short_shift = Shift(
        user_id=short_cashier.id,
        start_time=datetime.now(),
        end_time=datetime.now(),
        starting_cash=Decimal("5000.00"),
        expected_cash=Decimal("10000.00"),
        actual_cash=Decimal("9800.00"),
        status=ShiftStatus.CLOSED,
        terminal_id="TERM-01",
        reason_category="MISCOUNTED",
        notes="Short by 200",
    )
    over_shift = Shift(
        user_id=over_cashier.id,
        start_time=datetime.now(),
        end_time=datetime.now(),
        starting_cash=Decimal("5000.00"),
        expected_cash=Decimal("8000.00"),
        actual_cash=Decimal("8150.00"),
        status=ShiftStatus.CLOSED,
        terminal_id="TERM-01",
    )
    db_session.add_all([short_shift, over_shift])
    db_session.commit()
    return short_cashier, over_cashier, short_shift, over_shift


class TestShiftVarianceReport:
    def test_generates_a_row_per_closed_shift_with_status_and_reason(self, db_session, two_cashiers):
        short_cashier, over_cashier, _short_shift, _over_shift = two_cashiers

        df = ShiftVarianceReport().generate({})

        assert len(df) == 2
        short_row = df[df["Cashier"] == short_cashier.username].iloc[0]
        over_row = df[df["Cashier"] == over_cashier.username].iloc[0]

        assert short_row["Status"] == "Short"
        assert short_row["Variance"] == pytest.approx(-200.0)
        assert short_row["Reason"] == "MISCOUNTED"

        assert over_row["Status"] == "Over"
        assert over_row["Variance"] == pytest.approx(150.0)

    def test_sorted_by_variance_magnitude_largest_first(self, db_session, two_cashiers):
        df = ShiftVarianceReport().generate({})

        assert abs(df.iloc[0]["Variance"]) >= abs(df.iloc[1]["Variance"])

    def test_cashier_filter_returns_only_that_users_shifts(self, db_session, two_cashiers):
        short_cashier, _over_cashier, _short_shift, _over_shift = two_cashiers

        df = ShiftVarianceReport().generate({"user_id": short_cashier.id})

        assert len(df) == 1
        assert df.iloc[0]["Cashier"] == short_cashier.username

    def test_filter_definitions_include_all_cashiers_option(self, db_session, two_cashiers):
        filters = ShiftVarianceReport().get_filter_definitions()
        cashier_filter = next(f for f in filters if f["name"] == "user_id")

        assert cashier_filter["options"][0] == {"id": None, "label": "All Cashiers"}

    def test_registered_under_the_audit_category(self):
        from cbpos.core.reports import register_all_reports
        from cbpos.core.reports.registry import ReportRegistry

        register_all_reports()
        report = ReportRegistry().get_report_by_id("shift_variance")

        assert report is not None
        assert isinstance(report, ShiftVarianceReport)
