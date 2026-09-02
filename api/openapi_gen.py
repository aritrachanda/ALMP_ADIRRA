"""Generate openapi.json from the live FastAPI app schema."""
from __future__ import annotations

import json
from pathlib import Path

from api.main import app

_OUT = Path(__file__).resolve().parent / "openapi.json"


def main():
    schema = app.openapi()
    with _OUT.open("w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
