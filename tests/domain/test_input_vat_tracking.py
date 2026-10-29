"""
#489: TaxLiabilityReport showed Output VAT only -- Purchase/PurchaseItem
had no VAT field at all, so a shop owner using the report to estimate what
they owe overstated their liability by ignoring input VAT credits (VAT
already paid to suppliers, deductible against output VAT owed). Adds
Purchase.input_vat (entered manually at GRN commit time from the
supplier's invoice, not computed) and a net-liability summary row in the
report.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Permission, Product, Purchase, Role, Sale, SaleItem, Supplier, User
from cbpos.core.reports.definitions.financial_reports import TaxLiabilityReport
from cbpos.core.services.purchase_service import PurchaseService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"input_vat_test_{suffix}")
    role = Role(name=f"InputVatRole_{suffix}", permissions=[permission])
    user = User(username=f"input_vat_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Test Supplier {_counter}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"InputVatProduct_{_counter}",
        barcode=f"IVP{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("0"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestCommitPurchasePersistsInputVat:
    def test_input_vat_defaults_to_zero_when_not_provided(self, db_session, test_supplier, test_product, test_user):
        purchase = PurchaseService.create_purchase(test_supplier.id, "INV-001", test_user.id)
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("5"), "cost": Decimal("50")}]
        )

        db_session.expire_all()
        result = db_session.get(Purchase, purchase.id)
        assert result.input_vat == Decimal("0")

    def test_input_vat_is_persisted_when_provided(self, db_session, test_supplier, test_product, test_user):
        purchase = PurchaseService.create_purchase(test_supplier.id, "INV-002", test_user.id)
        PurchaseService.commit_purchase(
            purchase.id,
            [{"product_id": test_product.id, "qty": Decimal("10"), "cost": Decimal("50")}],
            input_vat=Decimal("76.27"),
        )

        db_session.expire_all()
        result = db_session.get(Purchase, purchase.id)
        assert result.input_vat == Decimal("76.27")


class TestTaxLiabilityReportNetLiability:
    def test_summary_row_deducts_input_vat_from_output_vat(self, db_session, test_supplier, test_product, test_user):
        sale = Sale(
            document_number="REC-IVT-001",
            date=datetime(2026, 1, 15),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("25.00"),
            net_revenue=Decimal("1000.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        sale_item = SaleItem(
            sale=sale,
            product_id=test_product.id,
            qty=1,
            unit_price=Decimal("1180.00"),
            original_price=Decimal("1180.00"),
            subtotal=Decimal("1180.00"),
        )
        db_session.add_all([sale, sale_item])
        db_session.commit()

        purchase = PurchaseService.create_purchase(test_supplier.id, "INV-003", test_user.id)
        PurchaseService.commit_purchase(
            purchase.id,
            [{"product_id": test_product.id, "qty": Decimal("10"), "cost": Decimal("50")}],
            input_vat=Decimal("50.00"),
        )
        db_session.commit()

        df = TaxLiabilityReport().generate({})
        summary_row = df[df["Invoice #"] == "NET VAT LIABILITY"].iloc[0]

        assert summary_row["VAT (18%)"] == Decimal("180.00")
        assert summary_row["Input VAT"] == Decimal("50.00")
        assert summary_row["Net VAT Liability"] == Decimal("130.00")

    def test_per_sale_rows_leave_input_vat_and_net_liability_blank(
        self, db_session, test_supplier, test_product, test_user
    ):
        sale = Sale(
            document_number="REC-IVT-002",
            date=datetime(2026, 1, 15),
            total_amount=Decimal("118.00"),
            user_id=test_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("100.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.commit()

        df = TaxLiabilityReport().generate({})
        sale_row = df[df["Invoice #"] == "REC-IVT-002"].iloc[0]

        assert sale_row["Input VAT"] is None
        assert sale_row["Net VAT Liability"] is None
