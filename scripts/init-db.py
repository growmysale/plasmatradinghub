"""Initialize PropEdge database."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from packages.backend.database import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
