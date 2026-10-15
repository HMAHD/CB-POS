"""#734: the transaction core runs headless -- importing it loads no Qt, print worker or printer service.

Checked in a fresh interpreter, because this test process already has Qt
and the printer code loaded by other tests.
"""

import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN = (
    "PyQt6",
    "cbpos.core.services.printer_service",
    "cbpos.infrastructure.hardware.escpos_driver",
    "cbpos.infrastructure.hardware.print_worker_peripherals",
)


def test_importing_the_transaction_service_loads_no_ui_or_printer_code():
    probe = (
        "import json, sys\n"
        "import cbpos.core.services.transaction_service\n"
        f"forbidden = {_FORBIDDEN!r}\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] == 'PyQt6' or m in forbidden)))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=120, check=True
    )

    assert json.loads(result.stdout.strip().splitlines()[-1]) == []
