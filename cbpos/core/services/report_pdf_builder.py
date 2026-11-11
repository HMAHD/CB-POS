"""Trilingual report PDF builder using ReportLab Platypus and shaped Noto fonts (#806).

Generates professional, paginated report PDFs with:
- Sinhala, Tamil, English and mixed-script text shaped natively via uharfbuzz.
- Repeated table headers across page breaks.
- Deterministic column widths proportional to content.
- Atomic file writing (leaves no partial or corrupted files on error).
- CB POS branding and page numbering on every page.
"""

import logging
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cbpos.core.utils.formatters import format_currency, format_quantity
from cbpos.i18n import _t
from cbpos.infrastructure.pdf_fonts import (
    create_cell_paragraph,
    escape_text,
    font_for,
    is_shaping_available,
    register_pdf_fonts,
)

logger = logging.getLogger(__name__)

_NAVY = colors.HexColor("#001F3F")
_TEAL = colors.HexColor("#00BCEB")
_BORDER = colors.HexColor("#E0E0E0")
_ROW_ALT = colors.HexColor("#F8F9FA")
_MUTED = colors.HexColor("#666666")


class ReportPDFBuilder:
    """Builds trilingual report PDFs from pandas DataFrames."""

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        filepath: str,
        title: str = "Report",
        filter_summary: str | None = None,
    ) -> str:
        """Export DataFrame to a styled, shaped PDF file atomically.

        Args:
            df: DataFrame containing the report data.
            filepath: Destination file path.
            title: Title of the report.
            filter_summary: Optional subtitle or filter summary string.

        Returns:
            The written file path.

        Raises:
            Exception: If PDF building fails; guarantees target file is not left in partial state.
        """
        register_pdf_fonts()
        target_path = Path(filepath).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Orientation & Margins
        num_cols = len(df.columns)
        is_landscape = num_cols > 5
        pagesize = landscape(A4) if is_landscape else A4
        margin = 12 * mm
        printable_width = pagesize[0] - (2 * margin)

        # 2. Atomic generation via temp file
        temp_fd, temp_path = tempfile.mkstemp(prefix="report_", suffix=".tmp.pdf", dir=str(target_path.parent))
        os.close(temp_fd)

        try:
            doc = SimpleDocTemplate(
                temp_path,
                pagesize=pagesize,
                leftMargin=margin,
                rightMargin=margin,
                topMargin=margin,
                bottomMargin=18 * mm,
            )

            story = []

            # 3. Title & Subtitle
            title_font = font_for(title)
            title_style = ParagraphStyle(
                name="ReportTitle",
                fontName=f"{title_font}-Bold",
                fontSize=14,
                leading=17,
                textColor=_NAVY,
                shaping=1 if is_shaping_available() else 0,
            )
            story.append(Paragraph(escape_text(title), title_style))
            story.append(Spacer(1, 2 * mm))

            # Generated timestamp & filter summary
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            meta_text = f"{_t('reports.generated_on', default='Generated on')}: {now_str}"
            if filter_summary:
                meta_text += f" · {filter_summary}"
            meta_font = font_for(meta_text)
            meta_style = ParagraphStyle(
                name="ReportMeta",
                fontName=meta_font,
                fontSize=8,
                leading=10,
                textColor=_MUTED,
                shaping=1 if is_shaping_available() else 0,
            )
            story.append(Paragraph(escape_text(meta_text), meta_style))
            story.append(Spacer(1, 5 * mm))

            # 4. Table Construction
            col_widths, col_alignments = cls._calculate_column_widths_and_alignments(df, printable_width)

            table_data = []

            # Header row
            header_row = []
            for col_idx, col_name in enumerate(df.columns):
                align = col_alignments[col_idx]
                p = create_cell_paragraph(str(col_name), bold=True, align=align, font_size=8)
                header_row.append(p)
            table_data.append(header_row)

            # Data rows or Empty state
            table_styles = [
                ("BACKGROUND", (0, 0), (-1, 0), _TEAL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]

            if df.empty:
                empty_msg = _t(
                    "common.no_records_found",
                    default="No records found for the selected period",
                )
                empty_p = create_cell_paragraph(empty_msg, align="center", font_size=8)
                empty_row = [empty_p] + [""] * (num_cols - 1)
                table_data.append(empty_row)
                table_styles.append(("SPAN", (0, 1), (-1, 1)))
                table_styles.append(("ALIGN", (0, 1), (-1, 1), "CENTER"))
            else:
                for row_idx, row in enumerate(df.itertuples(index=False), start=1):
                    row_cells = []
                    for col_idx, raw_val in enumerate(row):
                        align = col_alignments[col_idx]
                        formatted_str = cls._format_cell_value(raw_val, df.columns[col_idx])
                        p = create_cell_paragraph(formatted_str, bold=False, align=align, font_size=8)
                        row_cells.append(p)
                    table_data.append(row_cells)

                    # Alternating row background
                    if row_idx % 2 == 1:
                        table_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), _ROW_ALT))

            report_table = Table(
                table_data,
                colWidths=col_widths,
                repeatRows=1,
            )
            report_table.setStyle(TableStyle(table_styles))
            story.append(report_table)

            # 5. Build Document with Canvas Decorations
            def _draw_decorations(canvas: Any, doc_template: Any) -> None:
                canvas.saveState()
                # Center branding at bottom
                pw = getattr(doc_template, "pagesize", getattr(canvas, "_pagesize", (A4[0], A4[1])))[0]
                canvas.setFont("NotoSans", 8)
                canvas.setFillColor(_MUTED)
                canvas.drawCentredString(pw / 2, 8 * mm, "Powered by CB POS — ceybyte.com")
                # Page number
                page_num = (
                    canvas.getPageNumber() if hasattr(canvas, "getPageNumber") else getattr(canvas, "_pageNumber", 1)
                )
                canvas.drawRightString(pw - margin, 8 * mm, f"Page {page_num}")
                canvas.restoreState()

            doc.build(story, onFirstPage=_draw_decorations, onLaterPages=_draw_decorations)

            # Atomic replace
            os.replace(temp_path, str(target_path))
            return str(target_path)

        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            logger.error("Failed to build report PDF: %s", e)
            raise

    @classmethod
    def _calculate_column_widths_and_alignments(
        cls, df: pd.DataFrame, printable_width: float
    ) -> tuple[list[float], list[str]]:
        """Calculate column widths and alignments based on column types and printable space."""
        num_cols = len(df.columns)
        if num_cols == 0:
            return [], []

        alignments = []
        fixed_widths: list[float | None] = []
        flexible_weights: list[float] = []

        for col_name in df.columns:
            name_lower = str(col_name).lower()

            # Alignments
            is_numeric = False
            if any(
                term in name_lower
                for term in (
                    "qty",
                    "quantity",
                    "price",
                    "amount",
                    "total",
                    "subtotal",
                    "cost",
                    "vat",
                    "sscl",
                    "tax",
                    "balance",
                )
            ):
                alignments.append("right")
                is_numeric = True
            elif any(term in name_lower for term in ("no", "id", "code", "date", "status")):
                alignments.append("center")
            else:
                alignments.append("left")

            # Column Width categorization
            if any(term in name_lower for term in ("#", "no", "id", "code")) and not any(
                term in name_lower for term in ("product", "item", "barcode")
            ):
                fixed_widths.append(38.0)
                flexible_weights.append(0.0)
            elif any(term in name_lower for term in ("date", "time")):
                fixed_widths.append(72.0)
                flexible_weights.append(0.0)
            elif any(term in name_lower for term in ("qty", "quantity", "count")):
                fixed_widths.append(42.0)
                flexible_weights.append(0.0)
            elif any(term in name_lower for term in ("status", "method", "unit")):
                fixed_widths.append(50.0)
                flexible_weights.append(0.0)
            elif is_numeric:
                fixed_widths.append(65.0)
                flexible_weights.append(0.0)
            else:
                fixed_widths.append(None)
                weight = max(len(str(col_name)), 10)
                flexible_weights.append(weight)

        # Distribute remaining width
        total_fixed = sum(w for w in fixed_widths if w is not None)
        remaining_width = printable_width - total_fixed
        total_weight = sum(flexible_weights)

        col_widths = []
        for fixed, weight in zip(fixed_widths, flexible_weights, strict=True):
            if fixed is not None:
                col_widths.append(fixed)
            else:
                allocated = (
                    (weight / total_weight) * remaining_width if total_weight > 0 else (remaining_width / num_cols)
                )
                col_widths.append(max(allocated, 50.0))

        # Re-scale to ensure exact fit
        current_sum = sum(col_widths)
        if current_sum > 0:
            scale = printable_width / current_sum
            col_widths = [w * scale for w in col_widths]

        return col_widths, alignments

    @classmethod
    def _format_cell_value(cls, val: Any, col_name: str) -> str:
        """Format individual cell value based on column role and value type."""
        if val is None:
            return "—"
        try:
            if pd.isna(val):
                return "—"
        except Exception:
            pass

        col_lower = str(col_name).lower()
        if isinstance(val, (Decimal, float, int)):
            if any(term in col_lower for term in ("qty", "quantity")):
                return format_quantity(Decimal(str(val)))
            if any(
                term in col_lower
                for term in ("price", "amount", "total", "subtotal", "cost", "vat", "sscl", "tax", "balance")
            ):
                return format_currency(Decimal(str(val)))

        return str(val).strip()
