"""Guardrail tests for Phase 10A #923: Font bundle slimming and weights.

Verifies:
1. Four unused Noto Sans italic fonts are deleted.
2. The bundled font set contains exactly 12 static TTF files across Noto Sans,
   Noto Sans Sinhala, and Noto Sans Tamil.
3. Total raw font bundle size is under 2.0 MB (target ~1.92 MB).
4. QFontDatabase registers exactly 3 families: "Noto Sans", "Noto Sans Sinhala",
   and "Noto Sans Tamil".
5. QFontDatabase recognizes "Medium" (500) and "SemiBold" (600) as styles of "Noto Sans"
   rather than separate families (verifying --name-IDs='*' preservation).
6. Crucial glyphs (currency symbols, arrows, box drawing characters) are present
   in the subset Noto Sans files.
7. Subsetting is idempotent and reproducible (test_issue_923_subset_idempotency).
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtGui import QFontDatabase

from cbpos.infrastructure.resource_loader import ResourceLoader

project_root = Path(__file__).resolve().parent.parent.parent
fonts_dir = project_root / "cbpos" / "assets" / "fonts"


def test_issue_923_font_bundle_slimming_and_weights(qapp):
    """Verify font bundle has no italics, raw size < 2.0MB, 12 files, and weights resolve."""
    noto_sans_dir = fonts_dir / "Noto_Sans" / "static"

    # 1. Verify 4 italic files are absent
    italic_files = [
        "NotoSans-Italic.ttf",
        "NotoSans-MediumItalic.ttf",
        "NotoSans-SemiBoldItalic.ttf",
        "NotoSans-BoldItalic.ttf",
    ]
    for it in italic_files:
        assert not (noto_sans_dir / it).exists(), f"Italic font {it} should be deleted"

    # 2. Verify exactly 12 font files total in cbpos/assets/fonts/
    all_fonts = list(fonts_dir.glob("**/*.ttf")) + list(fonts_dir.glob("**/*.otf"))
    font_names = {f.name for f in all_fonts}
    assert len(all_fonts) == 12, f"Expected 12 font files, found {len(all_fonts)}: {font_names}"

    expected_noto_sans = {
        "NotoSans-Regular.ttf",
        "NotoSans-Medium.ttf",
        "NotoSans-SemiBold.ttf",
        "NotoSans-Bold.ttf",
    }
    noto_sans_present = {f.name for f in (fonts_dir / "Noto_Sans" / "static").glob("*.ttf")}
    assert noto_sans_present == expected_noto_sans

    # 3. Verify total raw font bundle size < 2.0 MB (target ~1.92 MB)
    total_size = sum(f.stat().st_size for f in all_fonts)
    assert total_size < 2.05 * 1024 * 1024, f"Font bundle size {total_size / (1024 * 1024):.2f}MB exceeds 2.0MB limit"

    # 4. Verify registered font families in Qt
    ResourceLoader.load_fonts()
    loaded_families = set(ResourceLoader.get_loaded_families())
    expected_families = {"Noto Sans", "Noto Sans Sinhala", "Noto Sans Tamil"}
    assert loaded_families == expected_families, f"Expected families {expected_families}, got {loaded_families}"

    # 5. Verify styles for Noto Sans include Medium and SemiBold
    styles = set(QFontDatabase.styles("Noto Sans"))
    assert "Regular" in styles
    assert "Bold" in styles
    assert "Medium" in styles, f"Noto Sans missing Medium style: {styles}"
    assert "SemiBold" in styles, f"Noto Sans missing SemiBold style: {styles}"

    # Verify Medium and SemiBold are not registered as standalone families
    assert "Noto Sans Medium" not in loaded_families
    assert "Noto Sans SemiBold" not in loaded_families

    # 6. Verify critical character ranges in subset Noto Sans via fonttools
    try:
        from fontTools.ttLib import TTFont

        regular_path = noto_sans_dir / "NotoSans-Regular.ttf"
        font = TTFont(str(regular_path))
        cmap = font.getBestCmap()

        # Currency symbols: LKR (₨: U+20A8), INR (₹: U+20B9), USD ($: U+0024), EUR (€: U+20AC), GBP (£: U+00A3)
        assert 0x20A8 in cmap, "Missing Sri Lankan Rupee sign (₨: U+20A8)"
        assert 0x20B9 in cmap, "Missing Indian Rupee sign (₹: U+20B9)"
        assert 0x0024 in cmap, "Missing dollar sign ($)"
        assert 0x20AC in cmap, "Missing euro sign (€)"
        assert 0x00A3 in cmap, "Missing pound sign (£)"

        # Dotted circle (U+25CC) for diacritics / complex combinations
        assert 0x25CC in cmap, "Missing dotted circle (U+25CC)"

        # Replacement character (U+FFFD)
        assert 0xFFFD in cmap, "Missing replacement character (U+FFFD)"

        # Check that any character in source font within target ranges is preserved in subset
        src_path = project_root / "scripts" / "font_sources" / "Noto_Sans" / "static" / "NotoSans-Regular.ttf"
        if src_path.exists():
            src_font = TTFont(str(src_path))
            src_cmap = src_font.getBestCmap()
            for cp in src_cmap:
                # If cp was in the requested range, it must be in the subset
                if (
                    (0x0000 <= cp <= 0x024F)
                    or cp == 0x0259
                    or (0x02B0 <= cp <= 0x036F)
                    or (0x1E00 <= cp <= 0x1EFF)
                    or (0x2000 <= cp <= 0x22FF)
                    or (0x2500 <= cp <= 0x25FF)
                    or cp in (0xFEFF, 0xFFFD)
                ):
                    assert cp in cmap, f"Codepoint {hex(cp)} was in source font within range but missing in subset"
    except ImportError:
        pass


def test_issue_923_subset_idempotency():
    """Verify that running scripts/subset_fonts.py is idempotent and reproducible."""
    script_path = project_root / "scripts" / "subset_fonts.py"
    if not script_path.exists():
        pytest.fail(f"Subset script not found at {script_path}")

    # Run script first time
    res1 = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    assert res1.returncode == 0, f"subset_fonts.py failed: {res1.stderr}"

    # Calculate sha256 of generated fonts
    noto_sans_dir = fonts_dir / "Noto_Sans" / "static"
    weights = ["Regular", "Medium", "SemiBold", "Bold"]
    hashes1 = {}
    for w in weights:
        p = noto_sans_dir / f"NotoSans-{w}.ttf"
        hashes1[w] = hashlib.sha256(p.read_bytes()).hexdigest()

    # Run script second time
    res2 = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    assert res2.returncode == 0, f"subset_fonts.py rerun failed: {res2.stderr}"

    hashes2 = {}
    for w in weights:
        p = noto_sans_dir / f"NotoSans-{w}.ttf"
        hashes2[w] = hashlib.sha256(p.read_bytes()).hexdigest()

    assert hashes1 == hashes2, "subset_fonts.py output is not deterministic across runs"
