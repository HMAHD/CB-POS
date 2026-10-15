"""#740: the A4 Tax Invoice builds, and says what a VAT-registered buyer needs.

``InvoiceService.generate_pdf`` read ``item.product.name``, ``item.quantity``
and ``item.discount`` -- fields Product / SaleItem don't have -- so every
invoice raised AttributeError: auto-print for VAT customers and Save PDF in
Receipt Options never produced one.

The sale here is built in memory (never in a session), like the detached
sale the peripherals print from. ConfigService is backed by a dict; the PDF
is real and read back with pypdf.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from pypdf import PdfReader

from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment, Unit
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService


@pytest.fixture
def settings(monkeypatch):
    values = dict(ConfigService.DEFAULTS)
    values.update(
        receipt_language="en",
        shop_name="Perera Hardware",
        shop_address="12 Main Street, Kandy",
        shop_phone="0812234567",
        vat_registered=True,
        vat_number="134567890-7000",
        company_tax_id="134567890",
        tax_vat_rate=18.0,
        tax_sscl_rate=2.5,
        company_bank_name="People's Bank",
        company_account_number="0041-55-321",
        company_bank_branch="Kandy",
    )
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


def _vat_sale() -> Sale:
    """Two lines (one discounted, one weighed), a Rs. 140 bill discount: Rs. 2,360 incl. VAT."""
    kg = Unit(name="Kilogram", abbreviation="kg", decimal_places=3)
    cement = Product(name_en="Cement 50kg", name_si="සිමෙන්ති 50kg", name_ta="சிமெண்ட் 50kg", price=Decimal("1200"))
    sugar = Product(name_en="Sugar (loose)", name_si="සීනි", price=Decimal("240"), unit=kg)
    sale = Sale(
        document_number="REC-000123",
        date=datetime(2026, 10, 15, 14, 30),
        total_amount=Decimal("2360.00"),
        tax_vat=Decimal("360.00"),
        tax_sscl=Decimal("25.00"),
        net_revenue=Decimal("1975.00"),
        additional_discount_type="FIXED",
        additional_discount_value=Decimal("140.00"),
        payment_method="CASH",
        status="COMPLETED",
        customer=Customer(
            name="Lanka Builders",
            address="45 Galle Road, Colombo 03",
            vat_number="114567890-7000",
            tax_id="114567890",
        ),
    )
    sale.items = [
        SaleItem(
            product=cement,
            qty=Decimal("2.000"),  # as reloaded from the Numeric(10, 3) column
            unit_price=Decimal("1100.00"),
            original_price=Decimal("1200.00"),
            subtotal=Decimal("2200.00"),
        ),
        SaleItem(
            product=sugar,
            qty=Decimal("1.250"),
            unit_price=Decimal("240.00"),
            original_price=Decimal("240.00"),
            subtotal=Decimal("300.00"),
        ),
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("2360.00"))]
    return sale


def _pdf_text(sale: Sale, tmp_path) -> str:
    pdf = tmp_path / "invoice.pdf"
    assert InvoiceService.generate_pdf(sale, str(pdf)) == str(pdf)
    return "\n".join(page.extract_text() for page in PdfReader(pdf).pages)


@pytest.mark.usefixtures("settings")
class TestInvoiceLines:
    def test_name_in_the_receipt_language_qty_in_unit_decimals_and_line_discount(self):
        cement, sugar = InvoiceService.invoice_lines(_vat_sale(), "si")

        assert cement.description == "සිමෙන්ති 50kg"
        assert cement.qty == "2"
        assert cement.unit_price == Decimal("1200.00")
        assert cement.discount == Decimal("200.00")
        assert cement.amount == Decimal("2200.00")

        assert sugar.description == "සීනි"
        assert sugar.qty == "1.250"
        assert sugar.discount == Decimal("0")
        assert sugar.amount == Decimal("300.00")

    def test_missing_translation_falls_back_to_english(self):
        _, sugar = InvoiceService.invoice_lines(_vat_sale(), "ta")

        assert sugar.description == "Sugar (loose)"


class TestVatInvoicePdf:
    def test_lines_totals_and_vat_breakdown(self, settings, tmp_path):
        text = _pdf_text(_vat_sale(), tmp_path)

        assert "TAX INVOICE" in text
        assert "REC-000123" in text
        assert "2026-10-15" in text
        for expected in ("Cement 50kg", "Sugar (loose)", "1.250", "1,200.00", "200.00", "2,200.00"):
            assert expected in text, expected
        # Sub total 2,700 - item discounts 200 - bill discount 140 = 2,360 incl. taxes
        for expected in ("2,700.00", "140.00", "2,360.00"):
            assert expected in text, expected
        # Backward from MRP: 2,360 = net 1,975 + VAT 360 + SSCL 25
        assert "VAT (18%)" in text
        assert "360.00" in text
        assert "SSCL (2.5%)" in text
        assert "25.00" in text
        assert "1,975.00" in text

    def test_shop_and_customer_vat_numbers(self, settings, tmp_path):
        text = _pdf_text(_vat_sale(), tmp_path)

        assert "Perera Hardware" in text
        assert "134567890-7000" in text  # shop VAT
        assert "Lanka Builders" in text
        assert "114567890-7000" in text  # customer VAT
        assert "114567890" in text  # customer TIN

    def test_bank_details_and_branding(self, settings, tmp_path):
        text = _pdf_text(_vat_sale(), tmp_path)

        assert "People's Bank" in text
        assert "0041-55-321" in text
        assert "CB POS" in text
        assert "ceybyte.com" in text


class TestNonVatInvoicePdf:
    def test_shop_not_vat_registered_gets_a_plain_invoice_without_vat_rows(self, settings, tmp_path):
        settings.update(vat_registered=False, vat_number="")
        sale = _vat_sale()
        sale.tax_vat = sale.tax_sscl = Decimal("0")
        sale.net_revenue = sale.total_amount
        sale.customer = None

        text = _pdf_text(sale, tmp_path)

        assert "TAX INVOICE" not in text
        assert "INVOICE" in text
        assert "VAT (" not in text
        assert "Walk-in" in text
        assert "2,360.00" in text
        assert "ceybyte.com" in text


@pytest.mark.usefixtures("app_fixture")
class TestInvoiceInSinhalaAndTamil:
    @pytest.mark.parametrize("lang", ["si", "ta"])
    def test_builds_in_the_receipt_language(self, settings, tmp_path, lang):
        settings["receipt_language"] = lang

        text = _pdf_text(_vat_sale(), tmp_path)

        # Sinhala/Tamil text is drawn with Qt (proper shaping); numbers and
        # Latin text stay selectable.
        assert "REC-000123" in text
        assert "2,360.00" in text
        assert "ceybyte.com" in text
