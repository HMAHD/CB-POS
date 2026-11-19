# Upstream Font Sources

This directory preserves the full unsubsetted original Noto Sans static fonts and checksums.
These fonts are licensed under the SIL Open Font License, Version 1.1.

Source: Google Fonts (Noto Sans)
Upstream version: 2.013; GOOG; pkg-noto-core-sans-latin-v2.013-40f4239

Files:
- `Noto_Sans/static/NotoSans-Regular.ttf`
- `Noto_Sans/static/NotoSans-Medium.ttf`
- `Noto_Sans/static/NotoSans-SemiBold.ttf`
- `Noto_Sans/static/NotoSans-Bold.ttf`
- `Noto_Sans/static/NotoSans-Italic.ttf`
- `Noto_Sans/static/NotoSans-MediumItalic.ttf`
- `Noto_Sans/static/NotoSans-SemiBoldItalic.ttf`
- `Noto_Sans/static/NotoSans-BoldItalic.ttf`

Usage:
`scripts/subset_fonts.py` reads from `scripts/font_sources/Noto_Sans/static/` and produces
the reproducible slim subsets in `cbpos/assets/fonts/Noto_Sans/static/`.

Note:
This directory is strictly excluded from the PyInstaller application bundle.

