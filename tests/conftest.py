"""Make scripts/config.py importable from the tests (single source of truth
for OLIST_DB_URL and the expected source row counts)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
