import pandas as pd
from xhtml2pdf import pisa


class ExportService:
    """
    Service to handle data export to various formats.
    """

    def export_to_excel(self, df: pd.DataFrame, filepath: str, title: str = "Report"):
        """
        Exports DataFrame to Excel with styling.
        """
        writer = pd.ExcelWriter(filepath, engine="xlsxwriter")
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

        writer.close()

    def export_to_csv(self, df: pd.DataFrame, filepath: str):
        """
        Exports DataFrame to CSV.
        """
        df.to_csv(filepath, index=False)

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
                <p>Generated on: {timestamp}</p>
                {table_html}
            </body>
            </html>
            """
        ).format(
            title=title,
            timestamp=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            table_html=table_html,
        )

        # Generate PDF
        with open(filepath, "wb") as result_file:
            pisa_status = pisa.CreatePDF(src=html_content, dest=result_file)

        if pisa_status.err:
            raise Exception(f"PDF generation failed: {pisa_status.err}")
