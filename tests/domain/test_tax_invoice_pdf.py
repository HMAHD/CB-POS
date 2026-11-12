"""PDF generation tests for official Sri Lankan VAT Tax Invoices (#814)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pypdf

from cbpos.core.models.tax_invoice import TaxInvoice, TaxInvoiceLine
from cbpos.core.services.tax_invoice_pdf_builder import TaxInvoicePDFBuilder


def _build_test_invoice(print_count: int = 0) -> TaxInvoice:
    inv = TaxInvoice(
        id=1,
        sale_id=101,
        serial="26OCT_MAIN_00001",
        issued_at=datetime(2026, 10, 15, 14, 30),
        supply_date=date(2026, 10, 15),
        payment_method="CASH",
        issued_by_user_id=1,
        supplier_name="Lanka Wholesale Emporium",
        supplier_address="100 Commercial Street, Pettah, Colombo 11",
        supplier_phone="+94 11 222 3333",
        supplier_tin="123456789",
        buyer_name="Ceylon Retailers Association",
        buyer_address="45 Galle Road, Colombo 03",
        buyer_phone="+94 11 999 8888",
        buyer_tin="987654321",
        issue_language="en",
        print_count=print_count,
        original_printed_at=datetime(2026, 10, 15, 14, 30) if print_count > 0 else None,
        subtotal_amount=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        net_amount=Decimal("1000.00"),
        tax_vat=Decimal("180.00"),
        total_amount=Decimal("1180.00"),
        amount_in_words="One Thousand One Hundred Eighty Rupees Only",
        lines=[
            TaxInvoiceLine(
                item_number=1,
                product_id=10,
                item_code_snapshot="SKU-001",
                product_name_snapshot="Premium Ceylon Tea 500g",
                unit_snapshot="pkt",
                quantity=Decimal("2.000"),
                unit_price=Decimal("500.00"),
                discount_amount=Decimal("0.00"),
                net_amount=Decimal("1000.00"),
                vat_rate=Decimal("18.00"),
                vat_amount=Decimal("180.00"),
                total_amount=Decimal("1180.00"),
            )
        ],
    )
    return inv


def test_tax_invoice_pdf_original(tmp_path: Path):
    """First issue/print of a Tax Invoice must prominently display 'TAX INVOICE' and 'ORIGINAL'."""
    inv = _build_test_invoice(print_count=0)
    pdf_path = tmp_path / "tax_inv_orig.pdf"

    generated = TaxInvoicePDFBuilder.generate_pdf(inv, str(pdf_path))
    assert Path(generated).exists()

    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()

    assert "TAX INVOICE" in text
    assert "ORIGINAL" in text
    assert "COPY ONLY" not in text

    # Statutory details
    assert "26OCT_MAIN_00001" in text
    assert "123456789" in text  # Supplier TIN
    assert "987654321" in text  # Buyer TIN
    assert "Lanka Wholesale Emporium" in text
    assert "Ceylon Retailers Association" in text
    assert "Premium Ceylon Tea" in text
    assert "500g" in text
    assert "One Thousand One Hundred Eighty Rupees Only" in text
    assert "1,180.00" in text


def test_tax_invoice_pdf_copy_only(tmp_path: Path):
    """Reprint of a Tax Invoice must prominently display 'COPY ONLY'."""
    inv = _build_test_invoice(print_count=1)
    pdf_path = tmp_path / "tax_inv_copy.pdf"

    generated = TaxInvoicePDFBuilder.generate_pdf(inv, str(pdf_path))
    assert Path(generated).exists()

    reader = pypdf.PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()

    assert "TAX INVOICE" in text
    assert "COPY ONLY" in text
    assert "26OCT_MAIN_00001" in text
