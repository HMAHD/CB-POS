import logging
from pathlib import Path

import pandas as pd
from xhtml2pdf import pisa

from cbpos.core.utils.spreadsheet_safety import XLSX_WRITER_OPTIONS, csv_safe
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class ExportService:
    """
    Service to handle data export to various formats.
    """

    @staticmethod
    def _validate_export_path(filepath: str) -> Path:
        """Validate export path to prevent path traversal attacks."""
        resolved = Path(filepath).resolve()
        if ".." in Path(filepath).parts:
            raise ValueError(f"Path traversal detected: {filepath}")
        import tempfile

        home = Path.home().resolve()
        temp_dir = Path(tempfile.gettempdir()).resolve()
        if not any(str(resolved).startswith(str(d)) for d in (home, temp_dir)):
            raise ValueError(f"Export path outside allowed directories: {filepath}")
        return resolved

    def export_to_excel(self, df: pd.DataFrame, filepath: str, title: str = "Report"):
        """
        Exports DataFrame to Excel with styling and formula injection safety (#898).
        """
        validated = self._validate_export_path(filepath)
        writer = pd.ExcelWriter(validated, engine="xlsxwriter", engine_kwargs={"options": XLSX_WRITER_OPTIONS})
        df.to_excel(writer, sheet_name="Sheet1", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        # Formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "fg_color": "#00BCEB",  # Cyan
                "font_color": "#FFFFFF",
                "border": 1,
            }
        )

        currency_format = workbook.add_format({"num_format": "#,##0.00"})

        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Auto-fit columns and apply currency format to likely currency columns
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
            worksheet.set_column(i, i, max_len)

            # Heuristic for currency/float columns
            if pd.api.types.is_float_dtype(df[col]):
                worksheet.set_column(i, i, max_len, currency_format)

        # Branding footer row
        footer_row = len(df) + 2  # +1 for header, +1 for blank row
        branding_format = workbook.add_format({"italic": True, "font_color": "#999999", "font_size": 8})
        worksheet.write(footer_row, 0, "Powered by CB POS — ceybyte.com", branding_format)

        writer.close()

    def export_to_csv(self, df: pd.DataFrame, filepath: str):
        """
        Exports DataFrame to CSV with formula injection safety (#898).
        """
        validated = self._validate_export_path(filepath)
        safe_df = df.map(csv_safe)
        safe_df.columns = [csv_safe(col) for col in df.columns]
        safe_df.to_csv(validated, index=False)

    def export_to_pdf(self, df: pd.DataFrame, filepath: str, title: str = "Report"):
        """
        Exports DataFrame to PDF using xhtml2pdf.
        """
        import textwrap

        # Convert DataFrame to HTML
        table_html = df.to_html(classes="table table-striped", index=False, border=0)

        # Simple HTML Template
        html_content = textwrap.dedent(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Helvetica, sans-serif; }}
                    h1 {{ color: #001F3F; }}
                    .table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    .table th {{ background-color: #00BCEB; color: white; padding: 8px; text-align: left; }}
                    .table td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                    .table tr:nth-child(even) {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <h1>{title}</h1>
                <p>{generated_on_label} {timestamp}</p>
                {table_html}
                <p style="text-align: center; color: #999; font-size: 9px; margin-top: 30px;">
                    Powered by CB POS &mdash; ceybyte.com
                </p>
            </body>
            </html>
            """
        ).format(
            title=title,
            generated_on_label=_t("report_viewer.generated_on"),
            timestamp=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            table_html=table_html,
        )

        # Generate PDF
        validated = self._validate_export_path(filepath)
        with open(validated, "wb") as result_file:
            pisa_status = pisa.CreatePDF(src=html_content, dest=result_file)

        if pisa_status.err:
            raise Exception(f"PDF generation failed: {pisa_status.err}")
