"""
Guardrail tests for rounding across the codebase (D4, #810).

Ensures all .quantize() calls in cbpos/core explicitly specify a rounding mode
(e.g., rounding=ROUND_HALF_UP) or use the approved round_money / round_qty helpers.
"""

import ast
from pathlib import Path

import pytest


@pytest.mark.guardrails
def test_no_quantize_without_rounding_mode_in_core():
    """
    Every call to .quantize() in cbpos/core must pass rounding= explicitly,
    excluding cbpos/core/utils/money.py which defines the single rounding authority.
    """
    core_dir = Path(__file__).resolve().parents[2] / "cbpos" / "core"
    money_file = (core_dir / "utils" / "money.py").resolve()

    violations = []
    scanned_count = 0

    for py_file in core_dir.rglob("*.py"):
        if py_file.resolve() == money_file:
            continue

        scanned_count += 1
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            pytest.fail(f"Could not parse {py_file}: {e}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check if this call is an attribute named 'quantize'
                if isinstance(node.func, ast.Attribute) and node.func.attr == "quantize":
                    has_rounding = any(kw.arg == "rounding" for kw in node.keywords) or len(node.args) >= 2
                    if not has_rounding:
                        violations.append(f"{py_file}:{node.lineno}")

    assert scanned_count > 10, f"Expected >10 Python files in cbpos/core, but only scanned {scanned_count}"

    assert not violations, (
        f"Found {len(violations)} .quantize() call(s) in cbpos/core without explicit rounding mode (D4/Issue #810):\n"
        + "\n".join(violations)
    )
