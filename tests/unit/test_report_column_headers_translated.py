"""Tests for report column header translations (#584).

Verifies that for every registered report in ReportRegistry:
1. Every column defined in report render_hints has a valid label_key.
2. In 'si' and 'ta', PandasModel.headerData() returns the translated label
   without falling back to the raw English column name or unflattened key.
"""

import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from cbpos.core.reports import register_all_reports
from cbpos.core.reports.registry import ReportRegistry
from cbpos.i18n import get_language, set_language
from cbpos.ui.views.reports.pandas_model import PandasModel

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def restore_language():
    prev_lang = get_language()
    yield
    set_language(prev_lang)


def test_all_16_reports_have_translated_column_headers_in_sinhala_and_tamil():
    register_all_reports()
    registry = ReportRegistry()

    reports = list(registry._all_reports.values())
    assert len(reports) >= 16, f"Expected at least 16 reports, found {len(reports)}"

    for lang in ("si", "ta"):
        set_language(lang)
        for report in reports:
            hints = report.get_render_hints()
            cols = hints.get("columns", {})
            assert cols, f"Report '{report.id}' ({report.name}) is missing columns render hint"

            # Create dummy DataFrame with matching columns
            df = pd.DataFrame({col_name: [None] for col_name in cols})
            model = PandasModel(df, hints)

            for col_idx, col_name in enumerate(df.columns):
                header_text = model.headerData(col_idx, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
                assert header_text is not None, f"Header for '{col_name}' in '{report.id}' returned None"
                assert not header_text.startswith("reports.col_"), (
                    f"Untranslated key '{header_text}' in '{report.id}' ({lang})"
                )
                # Ensure the header was translated and is not identical to the raw English name
                if col_name in ("Customer", "Phone", "Credit Limit", "Amount", "Current Stock", "Date", "Status"):
                    assert header_text != col_name, (
                        f"Column '{col_name}' in report '{report.id}' was not translated into {lang} (got '{header_text}')"
                    )


def test_all_report_column_keys_defined_in_all_languages():
    """Verify that every report column key is translated in en, si, and ta."""
    from cbpos.i18n import _t

    register_all_reports()
    registry = ReportRegistry()
    all_keys = set()
    for report in registry._all_reports.values():
        for col_def in report.get_render_hints().get("columns", {}).values():
            all_keys.add(col_def["label_key"])

    assert len(all_keys) >= 50

    for lang in ("en", "si", "ta"):
        set_language(lang)
        for key in sorted(all_keys):
            val = _t(key)
            assert val != key, f"Missing translation for '{key}' in '{lang}'"
