import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `api` and `core` are importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
