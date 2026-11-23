"""Regression tests for the reproducible Phase U UI inventory."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _inventory_module():
    """Load the audit tool after giving RED a behavior-level failure."""
    try:
        return importlib.import_module("scripts.phase_u_inventory")
    except ModuleNotFoundError:
        pytest.fail("scripts.phase_u_inventory is not implemented")


def _write_fixture_tree(tmp_path: Path) -> Path:
    root = tmp_path / "cbpos" / "ui"
    (root / "dialogs").mkdir(parents=True)
    (root / "widgets").mkdir()
    (root / "dialogs" / "alpha.py").write_text(
        """
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QDialog
from cbpos.core.database import Database
from cbpos.core.services.inventory_service import InventoryService

raise RuntimeError("the inventory must never import scanned modules")

class AlphaDialog(QDialog):
    def configure(self):
        self.setStyleSheet("color: #AABBCC; border: 1px solid #112233")

class AlphaWorker(QThread):
    pass
""".lstrip(),
        encoding="utf-8",
    )
    (root / "widgets" / "zeta.py").write_text(
        """
import cbpos.core.services.theme_service

class ZetaWidget:
    pass
""".lstrip(),
        encoding="utf-8",
    )
    return root


def test_scan_ui_tree_extracts_ast_signals_without_importing_modules(tmp_path: Path) -> None:
    """Catches importing UI code or dropping inventory fields during scanning."""
    inventory = _inventory_module()
    root = _write_fixture_tree(tmp_path)

    payload = inventory.scan_ui_tree(root, baseline_sha="abc123")

    assert payload["baseline_sha"] == "abc123"
    assert [record["path"] for record in payload["files"]] == [
        "cbpos/ui/dialogs/alpha.py",
        "cbpos/ui/widgets/zeta.py",
    ]
    assert payload["files"][0] == {
        "path": "cbpos/ui/dialogs/alpha.py",
        "role": "dialog",
        "line_count": 13,
        "classes": ["AlphaDialog", "AlphaWorker"],
        "core_service_imports": ["inventory_service"],
        "direct_database_import": True,
        "worker_classes": ["AlphaWorker"],
        "inline_stylesheet_calls": 1,
        "hex_literals": 2,
    }
    assert payload["files"][1]["core_service_imports"] == ["theme_service"]
    assert payload["summary"] == {
        "python_files": 2,
        "class_bearing_files": 2,
        "helper_only_files": 0,
        "top_level_classes": 3,
        "roles": {"dialog": 1, "reusable-widget": 1},
        "class_bearing_roles": {"dialog": 1, "reusable-widget": 1},
    }


def test_write_inventory_is_deterministic_utf8_json(tmp_path: Path) -> None:
    """Catches nondeterministic evidence that cannot be compared on final re-baseline."""
    inventory = _inventory_module()
    root = _write_fixture_tree(tmp_path)
    output = tmp_path / "evidence" / "ui_inventory.json"
    payload = inventory.scan_ui_tree(root, baseline_sha="abc123")

    inventory.write_inventory(payload, output)
    first = output.read_bytes()
    inventory.write_inventory(payload, output)

    assert output.read_bytes() == first
    assert first.endswith(b"\n")
    assert json.loads(first)["files"][0]["classes"] == ["AlphaDialog", "AlphaWorker"]


def test_check_mode_detects_drift_and_accepts_regenerated_evidence(tmp_path: Path) -> None:
    """Catches stale checked-in evidence after UI source changes."""
    inventory = _inventory_module()
    root = _write_fixture_tree(tmp_path)
    output = tmp_path / "ui_inventory.json"
    args = ["--root", str(root), "--baseline-sha", "abc123", "--output", str(output)]

    assert inventory.main(args) == 0
    assert inventory.main([*args, "--check"]) == 0

    source = root / "widgets" / "zeta.py"
    source.write_text(source.read_text(encoding="utf-8") + "\nclass AddedLater:\n    pass\n", encoding="utf-8")

    assert inventory.main([*args, "--check"]) == 1
