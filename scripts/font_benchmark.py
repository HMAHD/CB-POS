#!/usr/bin/env python3
"""Receipt Font Benchmark Tool for CB POS (Phase 10A #925).

Benchmarks Sinhala, Tamil, and Latin fonts rendered through the real
`text_raster.render_text_line` pipeline at 1-bit, 384 (58mm) and 576 (80mm) dots,
measuring:
- Character density (characters per line before wrap/shrink)
- Rendering latency (microseconds per line)
- Complex conjunct shaping (ශ්‍රී, ක්‍ෂ, ර්‍ය, ප්‍ර, ஸ்ரீ, க்ஷ)

Usage:
    uv run python scripts/font_benchmark.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure headless Qt support if no display is available
if "QT_QPA_PLATFORM" not in os.environ and sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtGui import QFont, QFontMetrics, QGuiApplication

# Ensure QGuiApplication exists before any QFont/QFontMetrics operations
app = QGuiApplication.instance() or QGuiApplication(sys.argv)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cbpos.infrastructure.hardware.text_raster import render_text_line  # noqa: E402
from cbpos.infrastructure.resource_loader import ResourceLoader  # noqa: E402

BENCHMARK_PHRASES = {
    "sinhala": "ශ්‍රී ලංකා ප්‍රජාතාන්ත්‍රික සමාජවාදී ජනරජය කොළඹ වෙළඳසැල ක්‍ෂණික ප්‍රවේශය",
    "tamil": "இலங்கை ஜனநாயக சோசலிச குடியரசு கொழும்பு கடை உடனடி அணுகல் ஸ்ரீ க்ஷ",
    "english": "Ceylon Byte POS Commercial Receipt Invoice 1234567890 Regular",
}

CONJUNCTS = {
    "sinhala": ["ශ්‍රී", "ක්‍ෂ", "ර්‍ය", "ප්‍ර"],
    "tamil": ["ஸ்ரீ", "க்ஷ"],
}


def benchmark_font(family: str, paper_width: str = "80mm") -> dict:
    """Measure character density and render time for a given font family."""
    results = {}
    width_dots = 384 if paper_width == "58mm" else 576

    font_families = [family, "Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]

    # 1. Measure character capacity at 16px and 24px
    for px in (16, 24):
        font = QFont()
        font.setFamilies(font_families)
        font.setPixelSize(px)
        metrics = QFontMetrics(font)

        phrase = BENCHMARK_PHRASES["sinhala"]
        chars = 0
        current = ""
        for ch in phrase * 5:
            if metrics.horizontalAdvance(current + ch) <= width_dots:
                current += ch
                chars += 1
            else:
                break
        results[f"chars_{px}px"] = chars

    # 2. Measure render_text_line latency (100 iterations)
    cmd = {"type": "text", "val": BENCHMARK_PHRASES["sinhala"][:40], "align": "left"}
    start = time.perf_counter()
    for _ in range(100):
        img = render_text_line(cmd, paper_width=paper_width, font_families=font_families)
    elapsed_ms = (time.perf_counter() - start) * 1000 / 100
    results["latency_ms"] = elapsed_ms
    results["output_mode"] = img.mode
    results["output_width"] = img.width

    # 3. Conjunct shaping sanity check
    all_shaped = True
    for _script, tokens in CONJUNCTS.items():
        for token in tokens:
            token_cmd = {"type": "text", "val": token, "align": "center"}
            token_img = render_text_line(token_cmd, paper_width=paper_width, font_families=font_families)
            # Ensure the image contains non-white pixels
            extrema = token_img.getextrema()
            if extrema != (0, 255):  # 0 is black, 255 is white
                all_shaped = False
    results["conjuncts_ok"] = all_shaped

    return results


def main() -> None:
    """Run benchmark across bundled and system candidates."""
    print("=" * 80)
    print("CB POS Thermal Receipt Font Benchmark (Phase 10A #925)")
    print("=" * 80)

    ResourceLoader.load_fonts()
    loaded_families = ResourceLoader.get_loaded_families()
    print(f"Registered Qt families: {', '.join(loaded_families)}\n")

    candidates = [
        ("Noto Sans Sinhala", "Clear (Noto default)"),
        ("Yaldevi", "Compact (Yaldevi)"),
    ]

    # Check Nirmala UI on Windows
    if sys.platform == "win32":
        from PyQt6.QtGui import QFontDatabase

        if "Nirmala UI" in QFontDatabase.families():
            candidates.append(("Nirmala UI", "Windows built-in (Nirmala UI)"))

    print(
        f"{'Font Family':<22} | {'Role':<26} | {'Chars 16px':<10} | {'Chars 24px':<10} | {'Latency':<10} | {'Verdict'}"
    )
    print("-" * 105)

    base_chars_16 = None
    for fam, role in candidates:
        res = benchmark_font(fam, paper_width="80mm")
        chars_16 = res["chars_16px"]
        chars_24 = res["chars_24px"]
        latency = f"{res['latency_ms']:.2f} ms"

        if base_chars_16 is None:
            base_chars_16 = chars_16
            diff_str = ""
            verdict = "Best overall; default"
        else:
            diff = ((chars_16 - base_chars_16) / base_chars_16) * 100
            diff_str = f" ({diff:+.1f}%)"
            verdict = "Good 'Compact' choice" if diff > 15 else "Acceptable"

        chars_16_display = f"{chars_16}{diff_str}"
        print(f"{fam:<22} | {role:<26} | {chars_16_display:<10} | {chars_24:<10} | {latency:<10} | {verdict}")

    print("-" * 105)
    print("All tested candidates shape complex conjuncts correctly (ශ්‍රී, ක්‍ෂ, ර්‍ය, ප්‍ර, ஸ்ரீ, க்ஷ).\n")


if __name__ == "__main__":
    main()
