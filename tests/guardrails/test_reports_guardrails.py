"""
Guardrail tests for Decimal precision in reports (Issue #798, CLAUDE.md).

Scans cbpos/core/reports for forbidden float() calls on money.
Only explicitly allowed legacy call sites (which shrink per batch) or chart-rendering boundaries may convert to float.
"""

import ast
from pathlib import Path

import pytest


@pytest.mark.guardrails
def test_no_float_on_money_in_reports():
    """
    AST guardrail: cbpos/core/reports/definitions must not use float() for money.
    Any allowed entries must name their rationale and may only shrink as remediation proceeds.
    """
    reports_dir = Path(__file__).resolve().parents[2] / "cbpos" / "core" / "reports"

    # Allowlist of legacy files pending remediation in their respective batches.
    # financial_reports.py is remediated in Batch 6.3 (#798) and must have NO float() calls.
    ALLOWED_LEGACY_FILES = {
        "audit_reports.py",
        "credit_report.py",
        "inventory_reports.py",
        "overdue_report.py",
        "shift_variance_report.py",
    }

    violations = []
    scanned_files = 0

    for py_file in reports_dir.rglob("*.py"):
        rel_name = py_file.name
        scanned_files += 1

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            pytest.fail(f"Could not parse {py_file}: {e}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "float":
                    if rel_name in ALLOWED_LEGACY_FILES:
                        continue
                    violations.append(f"{py_file.relative_to(reports_dir.parent.parent)}:{node.lineno}")

    assert scanned_files > 5, f"Expected >5 report files, got {scanned_files}"
    assert not violations, f"Found {len(violations)} forbidden float() call(s) in reports (Issue #798):\n" + "\n".join(
        violations
    )
