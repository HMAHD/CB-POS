"""AST guardrail to ensure every permission code in Permissions is referenced and enforced."""

import ast
from pathlib import Path

from cbpos.core.constants.permissions import Permissions

# Temporary allow-list for tracked permission codes whose enforcement is implemented
# in subsequent issues within Batch 5.1. Each entry MUST be removed in that issue's commit.
_ALLOW_UNREFERENCED: dict[str, str] = {
    "REPORTS_VIEW_SALES": "Tracked in #880",
    "REPORTS_VIEW_PROFIT": "Tracked in #880",
    "PURCHASE_CREATE_GRN": "Tracked in #896",
}


def _get_all_permission_attributes() -> dict[str, str]:
    """Return all string permission attributes defined on the Permissions class: {ATTR_NAME: 'code.string'}."""
    return {
        key: getattr(Permissions, key)
        for key in dir(Permissions)
        if not key.startswith("_") and isinstance(getattr(Permissions, key), str) and "." in getattr(Permissions, key)
    }


def _collect_referenced_permission_attributes() -> set[str]:
    """Scan all Python files in cbpos/ using AST to find all Permissions.<ATTR> references."""
    cbpos_dir = Path(__file__).resolve().parents[2] / "cbpos"
    referenced = set()

    for py_file in cbpos_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        is_permissions_file = py_file.name == "permissions.py"

        for node in ast.walk(tree):
            # In permissions.py, skip the definition of the class Permissions itself
            if is_permissions_file and isinstance(node, ast.ClassDef) and node.name == "Permissions":
                continue

            if isinstance(node, ast.Attribute):
                if (isinstance(node.value, ast.Name) and node.value.id == "Permissions") or (
                    isinstance(node.value, ast.Attribute) and node.value.attr == "Permissions"
                ):
                    referenced.add(node.attr)

    return referenced


def test_every_permission_code_is_enforced():
    """Ensure every permission defined on Permissions is referenced outside the class definition, or explicitly allow-listed."""
    all_perms = _get_all_permission_attributes()
    referenced = _collect_referenced_permission_attributes()

    unreferenced = {}
    for attr, code in all_perms.items():
        if attr not in referenced and attr not in _ALLOW_UNREFERENCED:
            unreferenced[attr] = code

    assert not unreferenced, (
        f"Found {len(unreferenced)} unreferenced permission codes without justification in _ALLOW_UNREFERENCED: "
        f"{unreferenced}"
    )


def test_every_permission_group_code_exists_in_catalogue():
    """Ensure every permission code in Permissions.get_groups() is defined as a constant on Permissions."""
    all_codes = set(_get_all_permission_attributes().values())
    groups = Permissions.get_groups()

    for group_name, codes in groups.items():
        for code in codes:
            assert code in all_codes, f"Code '{code}' in group '{group_name}' is missing from Permissions constant"
