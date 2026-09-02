"""Run the mapping agent for banking → CRDM scoped to CRDM.input.Guarantee.

Usage:
    python tests/test_guarantee_mapping.py                  # with annotations
    python tests/test_guarantee_mapping.py --no-annotations # baseline without annotations
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "core"))
sys.path.insert(0, str(_ROOT / "agents"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from mapping_agent import load_catalog, map_source_to_target, save_mapping
from annotations import load_annotations

TARGET_TABLE = "CRDM.input.Guarantee"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarantee mapping test case")
    parser.add_argument("--no-annotations", action="store_true",
                        help="Run without annotations for baseline comparison")
    args = parser.parse_args()

    # Load project config
    import yaml
    with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
        project = yaml.safe_load(fh)

    agent_cfg = project.get("agent", {})
    source_dir = Path(_ROOT / project.get("paths", {}).get("source_catalogs", "sources"))
    target_dir = Path(_ROOT / project.get("paths", {}).get("target_catalogs", "targets"))

    src_catalog = load_catalog("banking", source_dir, kind="source")
    tgt_catalog = load_catalog("crdm", target_dir, kind="target")

    # Load annotations unless --no-annotations
    annotations = None
    tgt_annotations = None
    if not args.no_annotations:
        annotations = load_annotations("banking", source_dir)
        if annotations:
            n_tables = len(annotations.get("annotations", {}))
            print(f"Loaded source annotations: {n_tables} table(s)")
        else:
            print("No source annotations found.")
        tgt_annotations = load_annotations("crdm", target_dir)
        if tgt_annotations:
            n_tables = len(tgt_annotations.get("annotations", {}))
            print(f"Loaded target annotations: {n_tables} table(s)")
        else:
            print("No target annotations found.")

    print(f"\nMapping banking → CRDM (table: {TARGET_TABLE})")
    print(f"  Provider: {agent_cfg.get('provider')}, Model: {agent_cfg.get('model')}")
    if args.no_annotations:
        print("  Annotations: DISABLED (baseline)")
    print()

    mapping = map_source_to_target(
        src_catalog, tgt_catalog, agent_cfg,
        target_tables={TARGET_TABLE},
        source_annotations=annotations,
        target_annotations=tgt_annotations,
    )

    # Save result
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_baseline" if args.no_annotations else ""
    out_path = GOLDEN_DIR / f"banking_to_crdm_guarantee{suffix}.yaml"
    import yaml as _yaml
    with out_path.open("w", encoding="utf-8") as fh:
        _yaml.dump(mapping, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"\nSaved to {out_path}")

    # Print summary
    for table_result in mapping.get("tables", []):
        tbl = f"{table_result.get('target_schema', '?')}.{table_result.get('target_table', '?')}"
        columns = table_result.get("columns", [])
        mapped = sum(1 for c in columns if c.get("transformation_type") == "direct")
        derived = sum(1 for c in columns if c.get("transformation_type") == "derived")
        unmapped = sum(1 for c in columns if c.get("transformation_type") == "unmapped")
        confs = [c.get("confidence", 0.0) for c in columns if c.get("confidence")]
        avg_conf = sum(confs) / len(confs) if confs else 0.0

        print(f"\n  Table: {tbl}")
        print(f"  Columns: {len(columns)}")
        print(f"  Direct:  {mapped}  |  Derived: {derived}  |  Unmapped: {unmapped}")
        print(f"  Avg confidence: {avg_conf:.2f}")


if __name__ == "__main__":
    main()
