#!/usr/bin/env python3
"""Deterministic Third-Party Notices Generator for CB POS.

Derives the complete transitive runtime dependency closure from pyproject.toml
and uv.lock, extracts license metadata, incorporates reviewed overrides,
includes bundled third-party assets (Qt, PyQt, Font Awesome, fonts, icons),
and writes a deterministic, sorted THIRD_PARTY_NOTICES.txt file.

Fails closed if any runtime package has unknown or missing licence information.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reviewed overrides for packages where upstream metadata is absent on non-Windows
# build hosts, missing the License field, or embeds raw multi-line prose.
REVIEWED_OVERRIDES: dict[str, dict[str, str]] = {
    "colorama": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2010 Jonathan Hartley, Arnon Yaari",
        "project_url": "https://github.com/tartley/colorama",
        "license_text": (
            "Copyright (c) 2010 Jonathan Hartley, Arnon Yaari\n"
            "All rights reserved.\n\n"
            "Redistribution and use in source and binary forms, with or without\n"
            "modification, are permitted provided that the following conditions are met:\n\n"
            "* Redistributions of source code must retain the above copyright notice, this\n"
            "  list of conditions and the following disclaimer.\n\n"
            "* Redistributions in binary form must reproduce the above copyright notice,\n"
            "  this list of conditions and the following disclaimer in the documentation\n"
            "  and/or other materials provided with the distribution.\n\n"
            "* Neither the name of the copyright holders nor the names of its\n"
            "  contributors may be used to endorse or promote products derived from\n"
            "  this software without specific prior written permission.\n\n"
            'THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"\n'
            "AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE\n"
            "IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE\n"
            "DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE\n"
            "FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL\n"
            "DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR\n"
            "SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER\n"
            "CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,\n"
            "OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE\n"
            "OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
        ),
    },
    "pywin32": {
        "license": "PSF-2.0",
        "copyright": "Copyright (c) 1994-2008 Mark Hammond and contributors",
        "project_url": "https://github.com/mhammond/pywin32",
        "license_text": (
            "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n"
            "Copyright (c) 1994-2008 Mark Hammond and contributors.\n"
            "All rights reserved.\n\n"
            "Subject to the terms and conditions of this License Agreement, PSF hereby\n"
            "grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,\n"
            "analyze, test, perform and/or display publicly, prepare derivative works,\n"
            "distribute, and otherwise use this software in source or binary form."
        ),
    },
    "tzdata": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) Python Software Foundation",
        "project_url": "https://github.com/python/tzdata",
        "license_text": (
            "Copyright (c) Python Software Foundation\n\n"
            'Licensed under the Apache License, Version 2.0 (the "License");\n'
            "you may not use this file except in compliance with the License.\n"
            "You may obtain a copy of the License at\n\n"
            "    http://www.apache.org/licenses/LICENSE-2.0\n\n"
            "Unless required by applicable law or agreed to in writing, software\n"
            'distributed under the License is distributed on an "AS IS" BASIS,\n'
            "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
            "See the License for the specific language governing permissions and\n"
            "limitations under the License."
        ),
    },
    "aiosignal": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) 2019-2024 Nikolay Kim and aiohttp contributors",
        "project_url": "https://github.com/aio-libs/aiosignal",
    },
    "frozenlist": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) 2021-2024 Nikolay Kim and aiohttp contributors",
        "project_url": "https://github.com/aio-libs/frozenlist",
    },
    "multidict": {
        "license": "Apache-2.0",
        "copyright": "Copyright (c) 2016-2024 Andrew Svetlov and aiohttp contributors",
        "project_url": "https://github.com/aio-libs/multidict",
    },
    "markupsafe": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright 2010 Pallets",
        "project_url": "https://palletsprojects.com/p/markupsafe/",
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
    "python-dateutil": {
        "license": "Apache-2.0 OR BSD-3-Clause",
        "copyright": "Copyright (c) 2003-2011 Gustavo Niemeyer; Copyright (c) 2012-2014 Tomi Pieviläinen; Copyright (c) 2014-2024 Yaron de Leeuw",
        "project_url": "https://github.com/dateutil/dateutil",
    },
    "psycopg2-binary": {
        "license": "LGPL-3.0-or-later WITH exceptions",
        "copyright": "Copyright (C) 2001-2024 Federico Di Gregorio, Daniele Varrazzo",
        "project_url": "https://psycopg.org/",
    },
    "python-bidi": {
        "license": "LGPL-3.0-or-later",
        "copyright": "Copyright (C) 2008-2022 Meir Kriheli",
        "project_url": "https://github.com/MeirKriheli/python-bidi",
    },
    "pycryptodomex": {
        "license": "BSD-2-Clause AND Public Domain",
        "copyright": "Copyright (c) 2014-2024 Helder Eijs and PyCryptodome contributors",
        "project_url": "https://www.pycryptodome.org",
    },
    "pyusb": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2005-2024 Wander Lairson Costa",
        "project_url": "https://pyusb.github.io/pyusb/",
    },
    "qrcode": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2011 Lincoln Loop",
        "project_url": "https://github.com/lincolnloop/python-qrcode",
    },
    "tinycss2": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2013-2024 Simon Sapin, CourtBouillon",
        "project_url": "https://github.com/Kozea/tinycss2",
    },
    "webencodings": {
        "license": "BSD-3-Clause",
        "copyright": "Copyright (c) 2012 Geoffrey Sneddon",
        "project_url": "https://github.com/gsnedders/python-webencodings",
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
        "version": "6.11.2",
        "license": "GNU Lesser General Public License v3 (LGPLv3) / GNU GPLv3",
        "copyright": "Copyright (C) The Qt Company Ltd and other contributors.",
        "project_url": "https://www.qt.io",
        "notice": (
            "Qt is available under the GNU LGPL version 3 and GNU GPL version 3. "
            "Source code and build instructions for Qt are available from https://code.qt.io."
        ),
    },
]


def extract_project_url(dist: md.Distribution, pkg_name: str) -> str:
    """Extract canonical project URL, preferring Source, Repo, Homepage over chat/donation/issue links."""
    raw_urls = dist.metadata.get_all("Project-URL") or []
    parsed_urls: list[tuple[str, str]] = []
    for entry in raw_urls:
        if "," in entry:
            label, url = entry.split(",", 1)
            parsed_urls.append((label.strip(), url.strip()))
        elif ":" in entry:
            label, url = entry.split(":", 1)
            parsed_urls.append((label.strip(), url.strip()))

    source_urls: list[str] = []
    homepage_urls: list[str] = []
    doc_urls: list[str] = []
    fallback_urls: list[str] = []

    disfavored_keywords = {
        "chat",
        "gitter",
        "matrix",
        "discord",
        "donate",
        "sponsor",
        "issues",
        "issue",
        "tracker",
        "changelog",
        "changes",
        "conduct",
        "coverage",
        "ci",
    }

    for label, url in parsed_urls:
        lbl_lower = label.lower()
        if any(bad in lbl_lower for bad in disfavored_keywords):
            continue
        if any(src in lbl_lower for src in ["source", "repository", "repo", "github", "code"]):
            source_urls.append(url)
        elif any(home in lbl_lower for home in ["home", "homepage", "web"]):
            homepage_urls.append(url)
        elif any(doc in lbl_lower for doc in ["doc", "docs", "documentation"]):
            doc_urls.append(url)
        else:
            fallback_urls.append(url)

    if source_urls:
        return source_urls[0]
    if homepage_urls:
        return homepage_urls[0]

    home_page = dist.metadata.get("Home-page")
    if home_page and home_page.strip() and home_page.strip().lower() not in ("none", "unknown"):
        return home_page.strip()

    if doc_urls:
        return doc_urls[0]
    if fallback_urls:
        return fallback_urls[0]

    return f"https://pypi.org/project/{pkg_name}"


def extract_license_text(dist: md.Distribution) -> str | None:
    """Extract full shipped license/notice text from installed package distribution files."""
    if not dist.files:
        return None

    candidate_files = []
    for f in dist.files:
        path_str = str(f).lower()
        name_str = f.name.lower()
        if (
            name_str.startswith(("license", "copying", "notice", "licence"))
            or "/licenses/" in path_str
            or "\\licenses\\" in path_str
        ):
            candidate_files.append(f)

    if not candidate_files:
        return None

    texts: list[str] = []
    for cf in candidate_files:
        try:
            content = cf.read_text(encoding="utf-8").strip()
            if content and len(content) > 10:
                texts.append(f"--- Shipped Notice ({cf.name}) ---\n{content}")
        except Exception:
            continue

    if texts:
        return "\n\n".join(texts)
    return None


def get_runtime_closure(lock_path: Path) -> dict[str, str]:
    """Parse uv.lock and compute the complete transitive runtime dependency closure.

    Resolves packages for the release target (Windows x86_64, CPython 3.12).
    Fails closed if duplicate locked versions cannot be deterministically resolved.

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

    # Resolve pinned version for each package in closure
    closure_versions: dict[str, str] = {}
    for name in closure:
        pkgs = packages_by_name.get(name, [])
        if not pkgs:
            raise RuntimeError(f"Package '{name}' in closure but not found in uv.lock packages")
        if len(pkgs) == 1:
            closure_versions[name] = pkgs[0].get("version", "pinned")
        else:
            # Ambiguous versions: target Windows x86_64, CPython 3.12 or fail closed
            selected = None
            for p in pkgs:
                markers = p.get("resolution-markers", "")
                if "win32" in markers or "windows" in markers.lower():
                    selected = p
                    break
            if selected is None:
                raise RuntimeError(
                    f"Ambiguous locked versions for package '{name}': {[p.get('version') for p in pkgs]}. "
                    "Cannot deterministically select release target version."
                )
            closure_versions[name] = selected.get("version", "pinned")

    return closure_versions


def extract_package_notice(pkg_name: str, pinned_version: str) -> dict[str, str]:
    """Extract license, copyright, project URL, and license text for a single package.

    Fails closed if license metadata is absent or unresolvable.
    """
    override = REVIEWED_OVERRIDES.get(pkg_name, {})

    license_id: str | None = override.get("license")
    copyright_notice: str | None = override.get("copyright")
    project_url: str | None = override.get("project_url")
    license_text: str | None = override.get("license_text")
    summary: str = ""
    display_name: str = pkg_name

    try:
        dist = md.distribution(pkg_name)
        display_name = dist.metadata.get("Name") or pkg_name

        if not license_id:
            # 1. Prefer modern validated License-Expression (PEP 639)
            raw_expr = dist.metadata.get("License-Expression")
            if raw_expr and raw_expr.strip() and raw_expr.strip() != "UNKNOWN":
                license_id = raw_expr.strip()

        if not license_id:
            # 2. Check Trove classifiers for standardized license identifiers
            classifiers = [
                c.split("::")[-1].strip() for c in (dist.metadata.get_all("Classifier") or []) if "License ::" in c
            ]
            if classifiers:
                license_id = classifiers[0]

        if not license_id:
            # 3. Fall back to License field if single short identifier (not prose paragraph)
            raw_lic = dist.metadata.get("License")
            if raw_lic and raw_lic.strip() and raw_lic.strip() != "UNKNOWN":
                lines = [line.strip() for line in raw_lic.splitlines() if line.strip()]
                if (
                    lines
                    and len(lines) == 1
                    and len(lines[0]) < 80
                    and not lines[0].lower().startswith(("copyright", "permission is hereby granted", "this software"))
                ):
                    license_id = lines[0]

        if not project_url:
            project_url = extract_project_url(dist, pkg_name)

        if not copyright_notice:
            author = dist.metadata.get("Author") or dist.metadata.get("Author-email")
            if author:
                copyright_notice = f"Author / Maintainer: {author}"

        summary = dist.metadata.get("Summary") or ""

        if not license_text:
            license_text = extract_license_text(dist)

    except md.PackageNotFoundError:
        # Expected on non-Windows build hosts for platform-conditional packages
        pass

    # Fail closed rule
    if not license_id:
        raise RuntimeError(
            f"Package '{pkg_name}' has unknown or missing licence information. "
            "Add a verified entry to REVIEWED_OVERRIDES in scripts/gen_third_party_notices.py."
        )

    return {
        "name": display_name,
        "version": pinned_version,
        "license": license_id,
        "copyright": copyright_notice or "Copyright holders and contributors",
        "project_url": project_url or f"https://pypi.org/project/{pkg_name}",
        "summary": summary,
        "license_text": license_text or "",
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
        if item.get("license_text"):
            lines.append("")
            lines.append(item["license_text"])
        lines.append("-" * 78)
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Generate or check THIRD_PARTY_NOTICES.txt."""
    parser = argparse.ArgumentParser(description="Deterministic Third-Party Notices Generator")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=ROOT / "THIRD_PARTY_NOTICES.txt",
        help="Path where notices file should be written",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the existing output file matches generated content without writing",
    )
    args = parser.parse_args(argv)

    try:
        content = generate_notices()
        output_path: Path = args.output
        if args.check:
            if not output_path.exists():
                print(f"ERROR: {output_path} does not exist for --check", file=sys.stderr)
                return 1
            existing = output_path.read_text(encoding="utf-8")
            if existing != content:
                print(
                    f"ERROR: {output_path} does not match generated content. "
                    "Run python scripts/gen_third_party_notices.py to regenerate.",
                    file=sys.stderr,
                )
                return 1
            print(f"OK: {output_path} is up to date.")
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"Successfully generated {output_path} ({len(content.splitlines())} lines)")
        return 0
    except Exception as exc:
        print(f"ERROR: Failed to generate third-party notices: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
