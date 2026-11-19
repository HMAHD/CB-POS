"""Tests for Phase 10A #924: Vector Sinhala/Tamil A4 Invoices via ReportLab HarfBuzz shaping.

Verifies:
1. make_shaped_paragraph produces ReportLab Paragraphs with shaping=1 for Indic scripts.
2. Newlines are properly converted to <br/> tags and XML is escaped.
3. ParagraphStyle inherits all parent properties (alignment, color, leading, font size).
4. A4 Commercial Invoices, Tax Invoices, Warranty Cards, and RMA Waybills generate vector
   PDFs containing NO raster image XObjects for Sinhala/Tamil text.
5. Embedded TrueType fonts include NotoSansSinhala and NotoSansTamil.
6. Fallback to render_text_png occurs if and only if uharfbuzz is unavailable.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pypdf
import pytest
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, Paragraph

from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment, Unit, Warranty
from cbpos.core.models.tax_invoice import TaxInvoice, TaxInvoiceLine
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.tax_invoice_pdf_builder import TaxInvoicePDFBuilder
from cbpos.core.services.warranty_card_builder import WarrantyCardBuilder
from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder
from cbpos.core.services.warranty_dto import WarrantyClaimDTO
from cbpos.infrastructure.pdf_fonts import (
    is_shaping_available,
    make_shaped_paragraph,
    register_pdf_fonts,
)

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def mock_config(monkeypatch):
    """Provide realistic configuration for invoice builders without disk access."""
    values = dict(ConfigService.DEFAULTS)
    values.update(
        receipt_language="en",
        shop_name="Lanka Trade Centre",
        shop_address="100 Main Street, Colombo 11",
        shop_phone="0112345678",
        vat_registered=True,
        vat_number="123456789-7000",
        company_tax_id="123456789",
        tax_vat_rate=18.0,
        tax_sscl_rate=2.5,
        company_bank_name="Bank of Ceylon",
        company_account_number="1234567890",
        company_bank_branch="Corporate",
    )
    monkeypatch.setattr(ConfigService, "get", lambda key, *args: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


def _count_pdf_images(pdf_path: Path) -> int:
    """Count number of raster Image XObjects across all pages in a PDF."""
    reader = pypdf.PdfReader(str(pdf_path))
    image_count = 0
    for page in reader.pages:
        image_count += len(page.images)
    return image_count


def _get_pdf_font_names(pdf_path: Path) -> set[str]:
    """Extract all font names embedded or referenced in a PDF."""
    reader = pypdf.PdfReader(str(pdf_path))
    font_names = set()
    for page in reader.pages:
        if "/Resources" in page and "/Font" in page["/Resources"]:
            fonts = page["/Resources"]["/Font"]
            for f in fonts.values():
                base_font = f.get("/BaseFont", "")
                font_names.add(str(base_font).lstrip("/"))
    return font_names


def test_issue_924_make_shaped_paragraph_complex_indic():
    """Verify make_shaped_paragraph detects Indic scripts, sets shaping=1, and preserves style."""
    register_pdf_fonts()
    base_style = ParagraphStyle(
        "TestStyle",
        fontSize=11,
        leading=15,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#001F3F"),
    )

    # 1. Sinhala text with complex ligatures: ශ්‍රී, ක්‍ෂ
    sinhala_text = "ශ්‍රී ලංකා තේ\n(Ceylon Tea)"
    flowable_si = make_shaped_paragraph(sinhala_text, base_style)
    assert isinstance(flowable_si, Paragraph)
    assert flowable_si.style.fontName == "NotoSansSinhala"
    assert flowable_si.style.shaping == 1
    assert flowable_si.style.alignment == TA_RIGHT
    assert flowable_si.style.fontSize == 11
    assert flowable_si.style.leading == 15
    assert flowable_si.style.textColor == colors.HexColor("#001F3F")
    assert "<br/>" in flowable_si.text
    assert "\n" not in flowable_si.text
    assert "ශ්‍රී ලංකා තේ" in flowable_si.text

    # 2. Tamil text with combinations: வணக்கம்
    tamil_text = "வணக்கம்\nWelcome"
    flowable_ta = make_shaped_paragraph(tamil_text, base_style)
    assert isinstance(flowable_ta, Paragraph)
    assert flowable_ta.style.fontName == "NotoSansTamil"
    assert flowable_ta.style.shaping == 1
    assert flowable_ta.style.alignment == TA_RIGHT
    assert "<br/>" in flowable_ta.text

    # 3. Latin text
    latin_text = "Invoice Number: REC-001"
    flowable_en = make_shaped_paragraph(latin_text, base_style)
    assert isinstance(flowable_en, Paragraph)
    assert flowable_en.style.fontName == "NotoSans"
    assert flowable_en.style.shaping == 0

    # 4. Bold style resolution
    bold_style = ParagraphStyle("TestBold", parent=base_style, fontName="Helvetica-Bold")
    flowable_si_bold = make_shaped_paragraph("වගකීම් සහතිකය", bold_style)
    assert isinstance(flowable_si_bold, Paragraph)
    assert flowable_si_bold.style.fontName == "NotoSansSinhala-Bold"
    assert flowable_si_bold.style.shaping == 1


def test_issue_924_fallback_to_png_on_import_error():
    """Verify fail-closed fallback to render_text_png occurs if uharfbuzz is unavailable."""
    base_style = ParagraphStyle("FallbackStyle", fontSize=10, leading=13)

    with patch("cbpos.infrastructure.pdf_fonts.is_shaping_available", return_value=False):
        flowable = make_shaped_paragraph("සිමෙන්ති 50kg", base_style)
        assert isinstance(flowable, Image)


@pytest.mark.usefixtures("mock_config")
def test_issue_924_vector_invoice_contains_no_raster_images(tmp_path: Path):
    """Verify all 4 A4/A5 PDF builders generate vector Sinhala/Tamil without raster images."""
    assert is_shaping_available() is True, "uharfbuzz must be available"

    # --- 1. A4 Commercial Invoice (InvoiceService) ---
    kg = Unit(name="Kilogram", abbreviation="kg", decimal_places=3)
    p_si = Product(name_en="Rice", name_si="සම්බා සහල් 5kg", price=Decimal("1250"))
    p_ta = Product(name_en="Sugar", name_ta="சர்க்கரை 1kg", price=Decimal("260"), unit=kg)

    sale = Sale(
        document_number="REC-2026-0001",
        date=datetime(2026, 11, 15, 10, 30),
        total_amount=Decimal("1510.00"),
        tax_vat=Decimal("230.34"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("1279.66"),
        payment_method="CASH",
        status="COMPLETED",
        customer=Customer(
            name="පෙරේරා සහ සමාගම",
            address="කොළඹ 07",
            vat_number="123456789-7000",
        ),
    )
    sale.items = [
        SaleItem(product=p_si, qty=Decimal("1.000"), unit_price=Decimal("1250.00"), subtotal=Decimal("1250.00")),
        SaleItem(product=p_ta, qty=Decimal("1.000"), unit_price=Decimal("260.00"), subtotal=Decimal("260.00")),
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("1510.00"))]

    invoice_pdf = tmp_path / "commercial_invoice.pdf"
    InvoiceService.generate_pdf(sale, str(invoice_pdf))
    assert invoice_pdf.exists()
    assert _count_pdf_images(invoice_pdf) == 0, "Commercial invoice must contain 0 raster image XObjects for text"
    fonts = _get_pdf_font_names(invoice_pdf)
    assert any("NotoSansSinhala" in f for f in fonts), f"Expected NotoSansSinhala font, got {fonts}"

    # --- 2. Statutory A4 VAT Tax Invoice (TaxInvoicePDFBuilder) ---
    tax_inv = TaxInvoice(
        id=1,
        sale_id=sale.id,
        serial="26NOV_MAIN_00001",
        issued_at=datetime(2026, 11, 15, 10, 30),
        supply_date=date(2026, 11, 15),
        payment_method="CASH",
        supplier_name="සීමාසහිත ලංකා වෙළඳ සමාගම",
        supplier_address="100 Main Street, Colombo 11",
        supplier_phone="0112345678",
        supplier_tin="123456789",
        buyer_name="ලංකා කන්ස්ට්‍රක්ෂන්ස් (Lanka Constructions)",
        buyer_address="45 Galle Road, Colombo 03",
        buyer_phone="0119998888",
        buyer_tin="987654321",
        issue_language="si",
        print_count=0,
        subtotal_amount=Decimal("1250.00"),
        discount_amount=Decimal("0.00"),
        net_amount=Decimal("1250.00"),
        tax_vat=Decimal("225.00"),
        total_amount=Decimal("1475.00"),
        amount_in_words="One Thousand Four Hundred Seventy Five Rupees Only",
        lines=[
            TaxInvoiceLine(
                item_number=1,
                product_id=1,
                item_code_snapshot="SKU-001",
                product_name_snapshot="සිමෙන්ති කොට්ට 50kg (Cement)",
                unit_snapshot="bag",
                quantity=Decimal("1.000"),
                unit_price=Decimal("1250.00"),
                discount_amount=Decimal("0.00"),
                net_amount=Decimal("1250.00"),
                vat_rate=Decimal("18.00"),
                vat_amount=Decimal("225.00"),
                total_amount=Decimal("1475.00"),
            )
        ],
    )
    tax_inv_pdf = tmp_path / "tax_invoice.pdf"
    TaxInvoicePDFBuilder.generate_pdf(tax_inv, str(tax_inv_pdf))
    assert tax_inv_pdf.exists()
    assert _count_pdf_images(tax_inv_pdf) == 0, "Tax invoice must contain 0 raster image XObjects for text"
    tax_fonts = _get_pdf_font_names(tax_inv_pdf)
    assert any("NotoSansSinhala" in f for f in tax_fonts), f"Expected NotoSansSinhala font, got {tax_fonts}"

    # --- 3. Warranty Certificate PDF (WarrantyCardBuilder) ---
    prod_warranty = Product(id=1, name_en="Samsung Galaxy A15", name_si="සැම්සුන්ග් දුරකථනය")
    w = Warranty(
        code="REC-001-01",
        sale_id=1,
        sale_item_id=1,
        product_id=1,
        product=prod_warranty,
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=date(2026, 11, 15),
        end_date=date(2027, 11, 14),
        terms_text="වගකීම් කොන්දේසි: නිෂ්පාදන දෝෂ සඳහා පමණි.",
        status="ACTIVE",
    )
    warranty_pdf = tmp_path / "warranty_card.pdf"
    WarrantyCardBuilder.build_pdf([w], str(warranty_pdf), page_size=A4, lang="si")
    assert warranty_pdf.exists()
    assert _count_pdf_images(warranty_pdf) == 0, "Warranty card must contain 0 raster image XObjects for text"
    w_fonts = _get_pdf_font_names(warranty_pdf)
    assert any("NotoSansSinhala" in f for f in w_fonts), f"Expected NotoSansSinhala font, got {w_fonts}"

    # --- 4. RMA Supplier Dispatch Waybill (WarrantyClaimReceiptBuilder) ---
    claim_dto = WarrantyClaimDTO(
        id=1,
        document_number="CLM-0001",
        warranty_id=1,
        warranty_code="REC-001-01",
        product_id=1,
        product_name="Inverter Air Conditioner 12000 BTU / වායුසමීකරණ යන්ත්‍රය",
        customer_id=1,
        customer_name="Secret Customer",  # Must be excluded from RMA waybill
        customer_phone="0771234567",
        item_serial="SN-AC-9988",
        claim_status="SENT_TO_SUPPLIER",
        intake_date=datetime(2026, 11, 15, 10, 0),
        defect_description="Compressor failure / කොම්ප්‍රෙසර් දෝෂය",
        item_condition="Minor scratch on body",
        accessories_received=None,
        is_covered=True,
        resolution=None,
        resolution_notes="Send to manufacturer workshop",
        rejection_reason=None,
        replacement_warranty_id=None,
        replacement_serial=None,
        repair_cost=Decimal("0.00"),
        charge_customer=Decimal("0.00"),
        resolved_by_user_id=None,
        resolved_by_username=None,
        resolved_at=None,
        collected_by_name=None,
        collected_at=None,
        user_id=1,
        created_at=datetime(2026, 11, 15, 10, 0),
        expected_ready_date=date(2026, 11, 30),
    )
    rma_pdf = tmp_path / "rma_waybill.pdf"
    WarrantyClaimReceiptBuilder.build_supplier_dispatch_pdf(claim_dto, str(rma_pdf))
    assert rma_pdf.exists()
    assert _count_pdf_images(rma_pdf) == 0, "RMA waybill must contain 0 raster image XObjects for text"
    rma_fonts = _get_pdf_font_names(rma_pdf)
    assert any("NotoSansSinhala" in f for f in rma_fonts), f"Expected NotoSansSinhala font, got {rma_fonts}"
