import os
import sys

sys.path.append(os.getcwd())

from cbpos.config import Config
from cbpos.core.database import Database

print(f"Original Config.DB_URI: {Config.DB_URI}")

# Test 1: Default (SQLite File)
Database._instance = None
try:
    db = Database()
    print("Test 1 (Default SQLite): Success")
except Exception as e:
    print(f"Test 1 (Default SQLite): Failed - {e}")

# Test 2: In-Memory SQLite
Config.DB_URI = "sqlite:///:memory:"
Database._instance = None
try:
    db = Database()
    print("Test 2 (Memory SQLite): Success")
except Exception as e:
    print(f"Test 2 (Memory SQLite): Failed - {e}")
