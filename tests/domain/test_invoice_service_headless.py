"""Services hold no PyQt: importing the A4 invoice service must not load Qt.

The invoice draws Sinhala/Tamil text with Qt (ReportLab can't shape it),
but only when such text is on the page -- the Qt renderer is imported
there, not at module load. Checked in a fresh interpreter so modules other
tests already imported can't hide a regression.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_importing_invoice_service_does_not_load_pyqt():
    code = (
        "import sys\n"
        "import cbpos.core.services.invoice_service\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'PyQt6'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120, check=True
    )

    assert result.stdout.strip() == "[]"
