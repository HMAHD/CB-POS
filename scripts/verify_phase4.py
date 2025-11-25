import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cbpos.core.services.cash_control_service import CashControlService  # noqa: E402
from cbpos.core.services.license_service import LicenseService  # noqa: E402
from cbpos.core.models import User  # noqa: E402
from cbpos.core.database import Database  # noqa: E402
from decimal import Decimal  # noqa: E402


def test_financials():
    print("Testing Financials...")
    db = Database()
    with db.get_session() as session:
        user = session.query(User).first()
        if not user:
            print("No user found to test with.")
            return

        print(f"User: {user.username}")

        # Start Shift
        shift = CashControlService.start_shift(user.id, Decimal("5000.00"))
        if shift:
            print(f"Shift Started: ID={shift.id}, Float={shift.start_float}")
        else:
            print("Shift already open or failed.")
            shift = CashControlService.get_current_shift(user.id)
            print(f"Using existing shift: ID={shift.id}")

        # Cash Movement
        CashControlService.record_cash_in(
            user.id, Decimal("1000.00"), "Petty Cash Topup"
        )
        print("Recorded Cash IN: 1000.00")

        CashControlService.record_cash_out(user.id, Decimal("500.00"), "Lunch")
        print("Recorded Cash OUT: 500.00")

        # End Shift
        closed_shift = CashControlService.end_shift(user.id, Decimal("5500.00"))
        if closed_shift:
            print(f"Shift Ended: End Cash={closed_shift.end_cash}")
        else:
            print("Failed to end shift.")


def test_license():
    print("\nTesting License...")
    mid = LicenseService.get_machine_id()
    print(f"Machine ID: {mid}")
    status = LicenseService.get_license_status()
    print(f"License Status: {status}")


if __name__ == "__main__":
    test_financials()
    test_license()
