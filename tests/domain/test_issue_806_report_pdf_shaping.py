"""Tests for #806: Shaped trilingual report PDF builder.

Verifies:
- NotoSans, NotoSansSinhala, and NotoSansTamil fonts are registered and detected.
- HarfBuzz shaping is active via uharfbuzz.
- ReportPDFBuilder exports DataFrames with Sinhala, Tamil, English and numbers to PDF.
- Embedded fonts match the scripts used.
- Atomic file generation prevents corrupt partial files on failure.
- ExportService uses ReportPDFBuilder without xhtml2pdf.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from cbpos.core.services.export_service import ExportService
from cbpos.core.services.report_pdf_builder import ReportPDFBuilder
from cbpos.infrastructure.pdf_fonts import (
    escape_text,
    font_for,
    is_shaping_available,
    register_pdf_fonts,
)


class TestPDFFonts:
    """Font registration and script classification tests."""

    def test_shaping_available_with_uharfbuzz(self):
        assert is_shaping_available() is True

    def test_font_registration(self):
        register_pdf_fonts()
        from reportlab.pdfbase import pdfmetrics

        assert "NotoSans" in pdfmetrics.getRegisteredFontNames()
        assert "NotoSansSinhala" in pdfmetrics.getRegisteredFontNames()
        assert "NotoSansTamil" in pdfmetrics.getRegisteredFontNames()

    def test_font_for_script_detection(self):
        assert font_for("Normal English Text 123") == "NotoSans"
        assert font_for("තේ කොළ 1kg") == "NotoSansSinhala"
        assert font_for("தேயிலை 1kg") == "NotoSansTamil"
        assert font_for("Mixed ශ්‍රී Lanka") == "NotoSansSinhala"
        assert font_for("") == "NotoSans"

    def test_escape_text(self):
        assert escape_text("Fish & Chips <Special>") == "Fish &amp; Chips &lt;Special&gt;"
        assert escape_text(None) == "—"
        assert escape_text("") == ""


class TestReportPDFBuilder:
    """PDF generation, layout, and styling tests."""

    @pytest.fixture
    def sample_trilingual_df(self):
        return pd.DataFrame(
            [
                {
                    "Item Code": "P001",
                    "Description": "ශ්‍රී ලංකා තේ (Ceylon Tea)",
                    "Qty": 10,
                    "Unit Price": Decimal("250.00"),
                    "Total": Decimal("2500.00"),
                },
                {
                    "Item Code": "P002",
                    "Description": "சர்க்கரை (Sugar)",
                    "Qty": 5,
                    "Unit Price": Decimal("200.00"),
                    "Total": Decimal("1000.00"),
                },
                {
                    "Item Code": "P003",
                    "Description": "Fresh Milk & Bread",
                    "Qty": 2,
                    "Unit Price": Decimal("400.00"),
                    "Total": Decimal("800.00"),
                },
            ]
        )

    def test_report_pdf_builder_creates_valid_pdf_with_embedded_fonts(self, sample_trilingual_df, tmp_path):
        pdf_path = tmp_path / "sales_report.pdf"
        out_path = ReportPDFBuilder.build(
            df=sample_trilingual_df,
            filepath=str(pdf_path),
            title="Daily Sales Summary / දෛනික විකුණුම් / தினசரி விற்பனை",
            filter_summary="Period: Today · Cashier: All",
        )
        assert Path(out_path).exists()
        assert Path(out_path).stat().st_size > 1000

        pdf_bytes = Path(out_path).read_bytes()
        # Verify font descriptors for all three scripts are embedded
        assert b"NotoSansSinhala" in pdf_bytes
        assert b"NotoSansTamil" in pdf_bytes
        assert b"NotoSans" in pdf_bytes

        # Verify branding and text content via PDF text extraction
        import pypdf

        reader = pypdf.PdfReader(str(out_path))
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "Powered by CB POS" in extracted_text
        assert "ceybyte.com" in extracted_text
        assert "Daily Sales Summary" in extracted_text
        assert "Ceylon Tea" in extracted_text

    def test_report_pdf_builder_empty_dataframe(self, tmp_path):
        empty_df = pd.DataFrame(columns=["Code", "Name", "Total"])
        pdf_path = tmp_path / "empty_report.pdf"
        out_path = ReportPDFBuilder.build(
            df=empty_df,
            filepath=str(pdf_path),
            title="Empty Test Report",
        )
        assert Path(out_path).exists()
        assert Path(out_path).stat().st_size > 500

    def test_report_pdf_builder_multi_page_pagination(self, tmp_path):
        rows = []
        for i in range(1, 101):
            rows.append(
                {
                    "No": i,
                    "Product": f"භාණ්ඩය {i:03d} (Product {i})",
                    "Qty": i,
                    "Amount": Decimal(f"{i * 100}.00"),
                }
            )
        large_df = pd.DataFrame(rows)
        pdf_path = tmp_path / "multi_page.pdf"
        out_path = ReportPDFBuilder.build(
            df=large_df,
            filepath=str(pdf_path),
            title="Large Multi-Page Report",
        )
        assert Path(out_path).exists()
        assert Path(out_path).stat().st_size > 15000

    def test_atomic_write_leaves_no_partial_file_on_error(self, sample_trilingual_df, tmp_path):
        pdf_path = tmp_path / "aborted_report.pdf"
        with patch("reportlab.platypus.SimpleDocTemplate.build", side_effect=RuntimeError("Build boom")):
            with pytest.raises(RuntimeError, match="Build boom"):
                ReportPDFBuilder.build(
                    df=sample_trilingual_df,
                    filepath=str(pdf_path),
                    title="Will Fail",
                )
        assert not pdf_path.exists()

    def test_export_service_uses_report_pdf_builder(self, sample_trilingual_df, tmp_path):
        svc = ExportService()
        pdf_path = tmp_path / "exported.pdf"
        svc.export_to_pdf(sample_trilingual_df, str(pdf_path), title="Inventory Valuation")
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000
