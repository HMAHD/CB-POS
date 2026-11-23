"""Generate the reproducible mechanical inventory used by Phase U.0."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

HEX_LITERAL = re.compile(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?(?:[0-9A-Fa-f]{2})?\b")
SERVICE_PREFIX = "cbpos.core.services"
DATABASE_MODULE = "cbpos.core.database"
WORKER_BASES = {"QThread", "QRunnable"}
WORKER_SUFFIXES = ("Worker", "Thread")


def _role(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    parts = relative.parts
    if relative.as_posix() == "main_window.py":
        return "shell"
    if "dialogs" in parts:
        return "dialog"
    if "settings_pages" in parts:
        return "settings-page"
    if "views" in parts:
        return "view"
    if "widgets" in parts:
        return "reusable-widget"
    if "components" in parts:
        return "shared-component"
    return "ui-infrastructure"


def _display_path(path: Path, root: Path) -> str:
    if root.name == "ui" and root.parent.name == "cbpos":
        return path.relative_to(root.parent.parent).as_posix()
    return path.relative_to(root).as_posix()


def _base_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    return ""


def _service_imports(tree: ast.AST) -> list[str]:
    services: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == SERVICE_PREFIX:
                services.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif node.module.startswith(f"{SERVICE_PREFIX}."):
                services.add(node.module.removeprefix(f"{SERVICE_PREFIX}.").split(".", 1)[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{SERVICE_PREFIX}."):
                    services.add(alias.name.removeprefix(f"{SERVICE_PREFIX}.").split(".", 1)[0])
    return sorted(services)


def _has_database_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == DATABASE_MODULE:
            return True
        if isinstance(node, ast.Import) and any(
            alias.name == DATABASE_MODULE or alias.name.startswith(f"{DATABASE_MODULE}.") for alias in node.names
        ):
            return True
    return False


def _scan_file(path: Path, root: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    worker_classes = [
        node.name
        for node in classes
        if node.name.endswith(WORKER_SUFFIXES) or any(_base_name(base) in WORKER_BASES for base in node.bases)
    ]
    inline_stylesheet_calls = sum(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setStyleSheet"
        for node in ast.walk(tree)
    )
    hex_literals = sum(
        len(HEX_LITERAL.findall(node.value))
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    return {
        "path": _display_path(path, root),
        "role": _role(path, root),
        "line_count": len(source.splitlines()),
        "classes": [node.name for node in classes],
        "core_service_imports": _service_imports(tree),
        "direct_database_import": _has_database_import(tree),
        "worker_classes": worker_classes,
        "inline_stylesheet_calls": inline_stylesheet_calls,
        "hex_literals": hex_literals,
    }


def scan_ui_tree(root: Path, baseline_sha: str) -> dict[str, object]:
    """Return a deterministic AST-only inventory of Python files below ``root``."""
    root = Path(root).resolve()
    records = [_scan_file(path, root) for path in sorted(root.rglob("*.py"))]
    roles = Counter(str(record["role"]) for record in records)
    class_bearing_roles = Counter(str(record["role"]) for record in records if record["classes"])
    class_count = sum(len(record["classes"]) for record in records)
    class_bearing = sum(bool(record["classes"]) for record in records)
    return {
        "schema_version": 1,
        "baseline_sha": baseline_sha,
        "root": "cbpos/ui" if root.name == "ui" and root.parent.name == "cbpos" else root.as_posix(),
        "summary": {
            "python_files": len(records),
            "class_bearing_files": class_bearing,
            "helper_only_files": len(records) - class_bearing,
            "top_level_classes": class_count,
            "roles": dict(sorted(roles.items())),
            "class_bearing_roles": dict(sorted(class_bearing_roles.items())),
        },
        "files": records,
    }


def _serialize(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def write_inventory(payload: dict[str, object], output: Path) -> None:
    """Write ``payload`` as deterministic UTF-8 JSON."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_serialize(payload), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the inventory or verify that checked-in evidence is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    payload = scan_ui_tree(args.root, args.baseline_sha)
    expected = _serialize(payload)
    if args.check:
        if not args.output.exists():
            print(f"ERROR: {args.output} does not exist", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != expected:
            print(f"ERROR: {args.output} is stale; regenerate it", file=sys.stderr)
            return 1
        print(f"OK: {args.output} is current")
        return 0

    write_inventory(payload, args.output)
    print(f"Wrote {len(payload['files'])} UI files to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
