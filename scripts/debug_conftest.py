import os
import sys

sys.path.append(os.getcwd())

# Import Config first to see what it is
from cbpos.config import Config

print(f"Initial Config.DB_URI: {Config.DB_URI}")

# Import conftest to trigger patching
import tests.conftest  # noqa: E402, F401

print(f"Patched Config.DB_URI: {Config.DB_URI}")

from cbpos.core.database import Database  # noqa: E402

# Manually trigger Database init
Database._instance = None
try:
    db = Database()
    print("Database initialized successfully.")
except Exception as e:
    print(f"Database initialization failed: {e}")
    import traceback

    traceback.print_exc()
