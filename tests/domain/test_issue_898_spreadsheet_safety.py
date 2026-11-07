"""Tests for Issue #898: Preventing formula injection in Excel and CSV exports."""

import csv

import openpyxl
import pandas as pd

from cbpos.core.services.export_service import ExportService
from cbpos.core.utils.spreadsheet_safety import csv_safe


def test_issue_898_csv_safe_prefixes_dangerous_characters():
    """Dangerous prefixes (=, +, -, @, \\t, \\r) on non-numeric strings are prefixed with '."""
    assert csv_safe("=SUM(A1:B1)") == "'=SUM(A1:B1)"
    assert csv_safe("+CMD|' /C calc'!A0") == "'+CMD|' /C calc'!A0"
    assert csv_safe("@SUM(1,2)") == "'@SUM(1,2)"
    assert csv_safe("\tTabbedValue") == "'\tTabbedValue"
    assert csv_safe("\rReturnVal") == "'\rReturnVal"
    assert csv_safe("-ItemDiscountCode") == "'-ItemDiscountCode"


def test_issue_898_negative_number_text_not_prefixed():
    """Negative and signed numeric strings are not prefixed and remain valid numbers."""
    assert csv_safe("-150.00") == "-150.00"
    assert csv_safe("-0.5") == "-0.5"
    assert csv_safe("+42") == "+42"
    assert csv_safe("+99.99") == "+99.99"
    assert csv_safe("0.00") == "0.00"
    assert csv_safe("Normal Product") == "Normal Product"
    assert csv_safe(123) == 123
    assert csv_safe(-45.67) == -45.67
    assert csv_safe(None) is None


def test_issue_898_xlsx_formula_text_is_string(tmp_path):
    """Excel export writes text starting with '=' as string cells (data_type 's'), never formulas ('f')."""
    svc = ExportService()
    export_file = str(tmp_path / "test_report.xlsx")

    df = pd.DataFrame(
        {
            "Product": ["=CMD|' /C calc'!A0", "=1+1", "Normal Apple", "-150.00"],
            "Price": [10.50, 20.00, 30.00, -150.00],
        }
    )

    svc.export_to_excel(df, export_file)

    wb = openpyxl.load_workbook(export_file)
    ws = wb["Sheet1"]

    # In openpyxl: row 1 is header, row 2 is first data row
    cmd_cell = ws.cell(row=2, column=1)
    calc_cell = ws.cell(row=3, column=1)
    normal_cell = ws.cell(row=4, column=1)
    neg_cell = ws.cell(row=5, column=1)

    assert cmd_cell.value == "=CMD|' /C calc'!A0"
    assert cmd_cell.data_type == "s"

    assert calc_cell.value == "=1+1"
    assert calc_cell.data_type == "s"

    assert normal_cell.value == "Normal Apple"
    assert normal_cell.data_type == "s"

    assert neg_cell.value == "-150.00"
    assert neg_cell.data_type == "s"


def test_issue_898_csv_formula_text_prefixed(tmp_path):
    """CSV export escapes dangerous text prefixes with ' while preserving numbers and headers."""
    svc = ExportService()
    export_file = str(tmp_path / "test_report.csv")

    df = pd.DataFrame(
        {
            "Product": ["=SUM(A1:A10)", "+cmd", "@lookup", "\tindented", "-discount_voucher", "Safe Name"],
            "Amount": ["-150.00", "+50.00", "0", 12.5, -99.9, 0],
        }
    )

    svc.export_to_csv(df, export_file)

    with open(export_file, encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    assert header == ["Product", "Amount"]

    rows = reader[1:]
    # Row 0: =SUM(A1:A10), -150.00
    assert rows[0][0] == "'=SUM(A1:A10)"
    assert rows[0][1] == "-150.00"

    # Row 1: +cmd, +50.00
    assert rows[1][0] == "'+cmd"
    assert rows[1][1] == "+50.00"

    # Row 2: @lookup, 0
    assert rows[2][0] == "'@lookup"
    assert rows[2][1] == "0"

    # Row 3: \tindented, 12.5
    assert rows[3][0] == "'\tindented"
    assert rows[3][1] == "12.5"

    # Row 4: -discount_voucher, -99.9
    assert rows[4][0] == "'-discount_voucher"
    assert rows[4][1] == "-99.9"

    # Row 5: Safe Name, 0
    assert rows[5][0] == "Safe Name"
    assert rows[5][1] == "0"
