from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Role, Supplier, SupplierLedgerEntry, User
from cbpos.core.services.supplier_payable_service import SupplierPayableService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"supp_test_perm_{_counter}")
    role = Role(name=f"SuppTestRole_{_counter}", permissions=[permission])
    user = User(username=f"supp_test_user_{_counter}", pin_hash="hash", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def test_issue_920_adjustment_ledger_sum_equals_payable(db_session, test_user):
    """An adjustment reducing payable below 0 must not clamp to 0; ledger and balance must reconcile (#920)."""
    supplier = Supplier(
        company_name="Acme Overcredit Supplier",
        current_payable=Decimal("3720.00"),
    )
    db_session.add(supplier)
    db_session.commit()

    # Record opening ledger entry to match initial payable
    opening = SupplierLedgerEntry(
        supplier_id=supplier.id,
        entry_type="PURCHASE",
        amount=Decimal("3720.00"),
        balance_after=Decimal("3720.00"),
        user_id=test_user.id,
        note="Initial invoice",
    )
    db_session.add(opening)
    db_session.commit()

    # Apply adjustment of -5000.00 (e.g. large credit note / return)
    SupplierPayableService.record_adjustment(
        supplier_id=supplier.id,
        amount=Decimal("-5000.00"),
        note="Credit note return",
        user_id=test_user.id,
    )

    db_session.refresh(supplier)
    ledger_entries = db_session.query(SupplierLedgerEntry).filter(SupplierLedgerEntry.supplier_id == supplier.id).all()
    ledger_sum = sum(e.amount for e in ledger_entries)

    # Invariant: ledger sum must equal current_payable (-1280.00)
    assert supplier.current_payable == Decimal("-1280.00"), (
        f"Expected supplier.current_payable to be -1280.00, got {supplier.current_payable}"
    )
    assert ledger_sum == Decimal("-1280.00"), f"Expected ledger_sum to be -1280.00, got {ledger_sum}"
    assert supplier.current_payable == ledger_sum
