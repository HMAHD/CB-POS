---
description: how to setup and run CB POS on macOS
---

1. Ensure **Homebrew** is installed.
2. Install system dependencies:
   ```bash
   brew install libusb cairo pkg-config
   ```
3. Install [uv](https://docs.astral.sh/uv/) if needed:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
4. Install Python dependencies:
   ```bash
   uv sync
   ```
   Creates `.venv` and installs the exact versions from `uv.lock` (qtawesome included).
5. Initialize the database:
   ```bash
   # Full reset and seed with default data
   uv run python scripts/seed.py
   ```
6. Run the application:
   ```bash
   uv run python main.py
   ```
