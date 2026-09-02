"""
build_dpm_cells.py – Build cell-level lookup JSON from DPM 2.0 YAML.

Parses dpm2.0.yaml and produces dpm_cells.json with structure:
  {table_code: [{row, col, datapoint}]}

This enables exact cell coordinate lookup by table code and datapoint keyword.

Usage:
    python rag/dpm/build_dpm_cells.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

INDEX_DIR = Path(__file__).resolve().parent
DPM_YAML = INDEX_DIR / "dpm2.0.yaml"


def _get_output_dir() -> Path:
    """Resolve RAG cache directory from project.yaml."""
    _ROOT = Path(__file__).resolve().parent.parent.parent
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    rag_cache = project.get("paths", {}).get("rag_cache", "~/.ai-timo/rag/")
    out = Path(rag_cache).expanduser() / "dpm"
    out.mkdir(parents=True, exist_ok=True)
    return out


def build_cells(yaml_path: Path) -> dict[str, list[dict]]:
    """Parse dpm2.0.yaml and return {table_code: [{row, col, datapoint}]}."""
    print(f"Parsing {yaml_path}...")
    with yaml_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    current_table_code = ""
    current_row = ""
    current_col = ""
    cells: dict[str, list[dict]] = {}

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("- table_code:"):
            current_table_code = stripped.split(":", 1)[1].strip()
            if current_table_code not in cells:
                cells[current_table_code] = []

        elif re.match(r"\{.+?,\s*r[\d*]+,\s*c\d+\}", stripped):
            # Cell coordinate line: {C_08.01.a, r0010, c0060}:
            coord_match = re.match(r"\{(.+?),\s*(r[\d*]+),\s*(c\d+)\}", stripped)
            if coord_match:
                current_row = coord_match.group(2)
                current_col = coord_match.group(3)

        elif "- items:" in stripped and current_table_code:
            match = re.search(r"\[(.+?)\]", stripped)
            if not match:
                continue
            items_path = match.group(1).strip()
            cells[current_table_code].append({
                "row": current_row,
                "col": current_col,
                "datapoint": items_path,
            })

    total = sum(len(v) for v in cells.values())
    print(f"  Tables: {len(cells)}")
    print(f"  Total cells: {total}")
    return cells


def main():
    cells = build_cells(DPM_YAML)

    output_dir = _get_output_dir()
    out_path = output_dir / "dpm_cells.json"
    print(f"Writing {out_path}...")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cells, f, ensure_ascii=False)

    print(f"Done! {out_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
