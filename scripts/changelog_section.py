#!/usr/bin/env python3
"""Extract a version section from CHANGELOG.md (#808).

Usage:
    python scripts/changelog_section.py <version> [changelog_path]

Example:
    python scripts/changelog_section.py 1.3.0
"""

import re
import sys
from pathlib import Path


def extract_changelog_section(version: str, changelog_text: str) -> str:
    """Extract markdown text for `version` from CHANGELOG markdown.

    Finds `## [version]` or `## [version] - date` and captures lines up to the
    next section starting with `## [`.
    """
    escaped_v = re.escape(version.lstrip("v"))
    pattern = rf"(?m)^##\s*\[{escaped_v}\](?:[^\n]*)?\n(.*?)(?=^##\s*\[|\Z)"
    match = re.search(pattern, changelog_text, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: changelog_section.py <version> [changelog_path]", file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]
    changelog_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("CHANGELOG.md")

    if not changelog_path.exists():
        print(f"Error: {changelog_path} does not exist", file=sys.stderr)
        sys.exit(1)

    content = changelog_path.read_text(encoding="utf-8")
    section = extract_changelog_section(version, content)
    if not section:
        print(f"Error: version [{version}] not found in {changelog_path}", file=sys.stderr)
        sys.exit(1)

    print(section)


if __name__ == "__main__":
    main()
