# /// script
# dependencies = ["fonttools>=4.50.0"]
# ///
"""Idempotent font subsetting script for CB POS (#923).

Subsets bundled Noto Sans Latin fonts (Regular, Medium, SemiBold, Bold) to:
- Basic Latin & Latin-1 Supplement (U+0000-024F)
- Latin Extended Additional & IPA extensions (U+0259, U+02B0-036F, U+1E00-1EFF)
- General Punctuation & Currency Symbols (U+2000-22FF, including ₨ and ₹)
- Box Drawing & Geometric Shapes (U+2500-25FF)
- Byte Order Mark (U+FEFF) & Replacement Character (U+FFFD)

Preserves typographic naming records (--name-IDs='*') so Qt resolves
Medium (500) and SemiBold (600) as styles of "Noto Sans".
Removes unused italic TTF files.
"""

import sys
from pathlib import Path

from fontTools.subset import main as subset_main
from fontTools.ttLib import TTFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "scripts" / "font_sources" / "Noto_Sans" / "static"
TARGET_DIR = PROJECT_ROOT / "cbpos" / "assets" / "fonts" / "Noto_Sans" / "static"
FONTS_DIR = PROJECT_ROOT / "cbpos" / "assets" / "fonts"

WEIGHTS = ["Regular", "Medium", "SemiBold", "Bold"]
ITALICS_TO_DELETE = [
    "NotoSans-Italic.ttf",
    "NotoSans-MediumItalic.ttf",
    "NotoSans-SemiBoldItalic.ttf",
    "NotoSans-BoldItalic.ttf",
]

UNICODES_RANGE = "U+0000-024F,U+0259,U+02B0-036F,U+1E00-1EFF,U+2000-22FF,U+2500-25FF,U+FEFF,U+FFFD"

ALL_BUNDLED_FAMILIES = [
    (
        "Noto_Sans",
        "Noto Sans",
        [("Regular", "Regular"), ("Medium", "Medium"), ("SemiBold", "SemiBold"), ("Bold", "Bold")],
    ),
    (
        "Noto_Sans_Sinhala",
        "Noto Sans Sinhala",
        [("Regular", "Regular"), ("Medium", "Medium"), ("SemiBold", "SemiBold"), ("Bold", "Bold")],
    ),
    (
        "Noto_Sans_Tamil",
        "Noto Sans Tamil",
        [("Regular", "Regular"), ("Medium", "Medium"), ("SemiBold", "SemiBold"), ("Bold", "Bold")],
    ),
]


def normalize_name_table(font_path: Path, family: str, style: str) -> None:
    """Normalize OpenType name table so FreeType/Qt registers family and styles uniformly."""
    tt = TTFont(font_path, recalcTimestamp=False)
    modified = False
    for record in tt["name"].names:
        enc = record.getEncoding()
        if not enc:
            continue
        if record.nameID == 1:
            val = family.encode(enc)
            if record.string != val:
                record.string = val
                modified = True
        elif record.nameID == 2:
            val = style.encode(enc)
            if record.string != val:
                record.string = val
                modified = True
        elif record.nameID == 4:
            val = f"{family} {style}".encode(enc)
            if record.string != val:
                record.string = val
                modified = True
        elif record.nameID == 16:
            val = family.encode(enc)
            if record.string != val:
                record.string = val
                modified = True
        elif record.nameID == 17:
            val = style.encode(enc)
            if record.string != val:
                record.string = val
                modified = True

    if modified:
        tt.save(font_path)


def subset_fonts():
    """Subset the 4 static Noto Sans weights, normalize name tables, and remove italic files."""
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source font directory not found at {SOURCE_DIR}")
        sys.exit(1)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Delete unused italic files from target directory
    for it in ITALICS_TO_DELETE:
        it_path = TARGET_DIR / it
        if it_path.exists():
            print(f"Deleting unused italic file: {it_path.name}")
            it_path.unlink()

    # 2. Subset each Noto Sans weight
    print("Subsetting Noto Sans weights...")
    for weight in WEIGHTS:
        source_file = SOURCE_DIR / f"NotoSans-{weight}.ttf"
        target_file = TARGET_DIR / f"NotoSans-{weight}.ttf"

        if not source_file.exists():
            print(f"ERROR: Missing source file {source_file}")
            sys.exit(1)

        src_size = source_file.stat().st_size
        args = [
            str(source_file),
            f"--output-file={target_file}",
            f"--unicodes={UNICODES_RANGE}",
            "--layout-features=*",
            "--name-IDs=*",
            "--name-languages=*",
            "--desubroutinize",
        ]
        subset_main(args)
        dst_size = target_file.stat().st_size
        print(
            f"  NotoSans-{weight}.ttf: {src_size / 1024:.1f} KB -> {dst_size / 1024:.1f} KB ({dst_size / src_size * 100:.1f}%)"
        )

    # 3. Normalize name tables across all bundled fonts (Noto Sans, Sinhala, Tamil)
    print("Normalizing OpenType name tables for uniform Qt family and style resolution...")
    for folder, family, weights in ALL_BUNDLED_FAMILIES:
        family_dir = FONTS_DIR / folder / "static"
        prefix = folder.replace("_", "")
        for weight_file, style_name in weights:
            font_path = family_dir / f"{prefix}-{weight_file}.ttf"
            if not font_path.exists():
                font_path = family_dir / f"NotoSans-{weight_file}.ttf"
            if font_path.exists():
                normalize_name_table(font_path, family, style_name)

    # 4. Print overall size summary
    all_fonts = list(FONTS_DIR.glob("**/*.ttf"))
    total_raw = sum(f.stat().st_size for f in all_fonts)
    print(f"\nFinal font bundle: {len(all_fonts)} files, {total_raw / (1024 * 1024):.2f} MB total.")


if __name__ == "__main__":
    subset_fonts()
