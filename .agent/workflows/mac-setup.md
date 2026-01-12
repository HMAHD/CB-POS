---
description: how to setup and run CB POS on macOS
---

1. Ensure **Homebrew** is installed.
2. Install system dependencies:
   ```bash
   brew install libusb cairo pkg-config
   ```
3. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   pip install qtawesome  # Required for GUI icons
   ```
5. Initialize the database:
   ```bash
   # Full reset and seed with default data
   python scripts/seed.py
   ```
6. Run the application:
   ```bash
   python main.py
   ```
