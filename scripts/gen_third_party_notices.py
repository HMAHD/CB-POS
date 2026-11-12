#!/usr/bin/env python3
"""Deterministic Third-Party Notices Generator for CB POS.

Derives the complete transitive runtime dependency closure from pyproject.toml
and uv.lock, extracts license metadata, incorporates reviewed overrides,
includes bundled third-party assets (Qt, PyQt, Font Awesome, fonts, icons),
and writes a deterministic, sorted THIRD_PARTY_NOTICES.txt file.

Fails closed if any runtime package has unknown or missing licence information.
"""

from __future__ import annotations

import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reviewed overrides for packages where upstream metadata is absent on non-Windows
# build hosts, missing the License field, or embeds raw multi-line text.
REVIEWED_OVERRIDES: dict[str, dict[str, str]] = {
    "colorama": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2010 Jonathan Hartley, Arnon Yaari",
        "project_url": "https://github.com/tartley/colorama",
    },
    "pywin32": {
        "license": "PSF-2.0",
        "copyright": "Copyright (c) 1994-2008 Mark Hammond and contributors",
        "project_url": "https://github.com/mhammond/pywin32",
    },
    "tzdata": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) Python Software Foundation",
        "project_url": "https://github.com/python/tzdata",
    },
    "cssselect2": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2012 Simon Sapin and contributors",
        "project_url": "https://github.com/Kozea/cssselect2",
    },
    "pandas": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2008-2011 AQR Capital Management, LLC, Lambda Foundry, Inc. and PyData Development Team; Copyright (c) 2011-2026 Open source contributors",
        "project_url": "https://pandas.pydata.org",
    },
    "reportlab": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2000-2024 ReportLab Inc.",
        "project_url": "https://www.reportlab.com/",
    },
    "xhtml2pdf": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) 2010-2024 xhtml2pdf contributors",
        "project_url": "https://github.com/xhtml2pdf/xhtml2pdf",
    },
}

# Bundled non-PyPI third-party assets (fonts, icons, graphics, frameworks)
BUNDLED_ASSETS: list[dict[str, str]] = [
    {
        "name": "Font Awesome Free (via QtAwesome)",
        "version": "5.15.4 / 6.x",
        "license": "SIL OFL 1.1 (fonts), CC BY 4.0 (icons), MIT License (code)",
        "copyright": "Copyright (c) Fonticons, Inc. and Font Awesome contributors",
        "project_url": "https://fontawesome.com/",
        "notice": (
            "Font Awesome Free is free, open source, and GPL-friendly. Icons are licensed under "
            "Creative Commons Attribution 4.0 International (CC BY 4.0), font files under the "
            "SIL Open Font License 1.1, and client code under the MIT License."
        ),
    },
    {
        "name": "Google Noto Sans Font Family",
        "version": "2.013",
        "license": "SIL Open Font License 1.1 (OFL-1.1)",
        "copyright": "Copyright 2012 Google LLC. All Rights Reserved.",
        "project_url": "https://fonts.google.com/noto",
        "notice": "Bundled TrueType fonts in cbpos/assets/fonts/Noto_Sans/ under SIL OFL 1.1.",
    },
    {
        "name": "Google Noto Sans Sinhala Font Family",
        "version": "2.004",
        "license": "SIL Open Font License 1.1 (OFL-1.1)",
        "copyright": "Copyright 2013 Google LLC. All Rights Reserved.",
        "project_url": "https://fonts.google.com/noto/specimen/Noto+Sans+Sinhala",
        "notice": "Bundled TrueType fonts in cbpos/assets/fonts/Noto_Sans_Sinhala/ under SIL OFL 1.1.",
    },
    {
        "name": "Google Noto Sans Tamil Font Family",
        "version": "2.004",
        "license": "SIL Open Font License 1.1 (OFL-1.1)",
        "copyright": "Copyright 2013 Google LLC. All Rights Reserved.",
        "project_url": "https://fonts.google.com/noto/specimen/Noto+Sans+Tamil",
        "notice": "Bundled TrueType fonts in cbpos/assets/fonts/Noto_Sans_Tamil/ under SIL OFL 1.1.",
    },
    {
        "name": "Lucide / UI SVG Icons",
        "version": "0.400+",
        "license": "MIT License",
        "copyright": "Copyright (c) 2022-2026 Lucide Contributors",
        "project_url": "https://lucide.dev",
        "notice": "Vector interface icons located under cbpos/assets/icons/.",
    },
    {
        "name": "Qt 6 (Libraries & Framework)",
        "version": "6.7.x / 6.8.x",
        "license": "GNU Lesser General Public License v3 (LGPLv3) / GNU GPLv3",
        "copyright": "Copyright (C) The Qt Company Ltd and other contributors.",
        "project_url": "https://www.qt.io",
        "notice": (
            "Qt is available under the GNU LGPL version 3 and GNU GPL version 3. "
            "Source code and build instructions for Qt are available from https://code.qt.io."
        ),
    },
]


def get_runtime_closure(lock_path: Path) -> dict[str, str]:
    """Parse uv.lock and compute the complete transitive runtime dependency closure.

    Returns:
        Mapping of lowercased package name to pinned version.
    """
    with lock_path.open("rb") as f:
        data = tomllib.load(f)

    packages_by_name: dict[str, list[dict]] = {}
    for pkg in data.get("package", []):
        name = pkg["name"].lower()
        packages_by_name.setdefault(name, []).append(pkg)

    if "cbpos" not in packages_by_name:
        raise RuntimeError("Root package 'cbpos' not found in uv.lock")

    cbpos_pkg = packages_by_name["cbpos"][0]
    direct_runtime_deps = [d["name"].lower() for d in cbpos_pkg.get("dependencies", [])]

    closure: set[str] = set(direct_runtime_deps)
    queue: list[str] = list(direct_runtime_deps)

    while queue:
        current = queue.pop(0)
        for pkg in packages_by_name.get(current, []):
            for dep in pkg.get("dependencies", []):
                dep_name = dep["name"].lower()
                if dep_name not in closure:
                    closure.add(dep_name)
                    queue.append(dep_name)

    # Get pinned version for each package in closure
    closure_versions: dict[str, str] = {}
    for name in closure:
        pkgs = packages_by_name.get(name, [])
        if pkgs and "version" in pkgs[0]:
            closure_versions[name] = pkgs[0]["version"]
        else:
            closure_versions[name] = "pinned"

    return closure_versions


def extract_package_notice(pkg_name: str, pinned_version: str) -> dict[str, str]:
    """Extract license, copyright, and project URL for a single package.

    Fails closed if license metadata is absent or unresolvable.
    """
    override = REVIEWED_OVERRIDES.get(pkg_name, {})

    license_id: str | None = override.get("license")
    copyright_notice: str | None = override.get("copyright")
    project_url: str | None = override.get("project_url")
    summary: str = ""

    # Attempt to query installed distribution metadata
    try:
        dist = md.distribution(pkg_name)
        if not license_id:
            raw_lic = dist.metadata.get("License-Expression") or dist.metadata.get("License")
            if raw_lic and raw_lic.strip() and raw_lic.strip() != "UNKNOWN":
                # If raw_lic is multi-line, take first line or clean up
                lines = [line.strip() for line in raw_lic.splitlines() if line.strip()]
                if lines and len(lines[0]) < 120:
                    license_id = lines[0]

        if not license_id:
            # Check Trove classifiers
            classifiers = [
                c.split("::")[-1].strip() for c in (dist.metadata.get_all("Classifier") or []) if "License ::" in c
            ]
            if classifiers:
                license_id = classifiers[0]

        if not project_url:
            project_url = dist.metadata.get("Project-URL") or dist.metadata.get("Home-page")
            if project_url and "," in project_url:
                project_url = project_url.split(",")[-1].strip()

        if not copyright_notice:
            author = dist.metadata.get("Author") or dist.metadata.get("Author-email")
            if author:
                copyright_notice = f"Author / Maintainer: {author}"

        summary = dist.metadata.get("Summary") or ""
    except Exception:
        # Package not installed in the current environment (e.g. cross-platform package)
        pass

    # Fail closed rule
    if not license_id:
        raise RuntimeError(
            f"Package '{pkg_name}' has unknown or missing licence information. "
            "Add a verified entry to REVIEWED_OVERRIDES in scripts/gen_third_party_notices.py."
        )

    # Format official display name if available
    display_name = pkg_name
    try:
        dist = md.distribution(pkg_name)
        display_name = dist.metadata.get("Name") or pkg_name
    except Exception:
        pass

    return {
        "name": display_name,
        "version": pinned_version,
        "license": license_id,
        "copyright": copyright_notice or "Copyright holders and contributors",
        "project_url": project_url or "https://pypi.org/project/" + pkg_name,
        "summary": summary,
    }


def generate_notices() -> str:
    """Generate deterministic, sorted third-party notices text."""
    lock_path = ROOT / "uv.lock"
    if not lock_path.exists():
        raise FileNotFoundError(f"uv.lock not found at {lock_path}")

    closure = get_runtime_closure(lock_path)

    package_notices: list[dict[str, str]] = []
    for pkg_name in sorted(closure.keys()):
        version = closure[pkg_name]
        notice = extract_package_notice(pkg_name, version)
        package_notices.append(notice)

    # Combine runtime packages and bundled assets
    all_entries = package_notices + BUNDLED_ASSETS
    all_entries.sort(key=lambda item: item["name"].lower())

    lines: list[str] = [
        "=" * 78,
        "CB POS — THIRD-PARTY SOFTWARE NOTICES & LICENSES",
        "=" * 78,
        "",
        "CB POS is free and open-source software distributed under the GNU General",
        "Public License version 3 (GPLv3).",
        "",
        "This file contains copyright notices, project URLs, and license terms for",
        "all runtime third-party packages, libraries, fonts, and assets incorporated",
        "into or distributed with CB POS.",
        "",
        f"Total third-party components documented: {len(all_entries)}",
        "",
        "=" * 78,
        "",
    ]

    for item in all_entries:
        lines.append(f"Component:    {item['name']}")
        lines.append(f"Version:      {item['version']}")
        lines.append(f"License:      {item['license']}")
        if "copyright" in item:
            lines.append(f"Copyright:    {item['copyright']}")
        if "project_url" in item:
            lines.append(f"URL:          {item['project_url']}")
        if "notice" in item:
            lines.append(f"Notice:       {item['notice']}")
        if item.get("summary"):
            lines.append(f"Summary:      {item['summary']}")
        lines.append("-" * 78)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Generate THIRD_PARTY_NOTICES.txt at the repository root."""
    try:
        content = generate_notices()
        output_path = ROOT / "THIRD_PARTY_NOTICES.txt"
        output_path.write_text(content, encoding="utf-8")
        print(f"Successfully generated {output_path} ({len(content.splitlines())} lines)")
        return 0
    except Exception as exc:
        print(f"ERROR: Failed to generate third-party notices: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
