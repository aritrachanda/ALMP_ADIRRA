"""
bird_mapping_agent.py  –  BIRD-aware target-driven mapping agent (Input Layer target).

Specialized variant of `mapping_agent.py` that targets the BIRD Input Layer (IL).
Reuses provider dispatch, throttling, retry, catalog loading and helpers from
the generic agent and adds:

  * A BIRD-grounded system prompt (vocabulary from .github/skills/bird/SKILL.md).
  * BIRD-aware source pre-filtering that boosts table-level scoring by
    `framework` and `role` overlap and respects an optional `layer` filter.
  * A richer per-column output schema:
      - `transformation_type`: "direct" | "derived" | "unmapped"
      - `notes` (optional): brief hint about the transformation
  * `target_framework` populated on each target table when known.
  * `sql_query` per target table.

Usage:
    python agents/bird_mapping_agent.py
    python agents/bird_mapping_agent.py --source banking
    python agents/bird_mapping_agent.py --source banking --target bird --dry-run

Output:
    mappings/<source>_to_<target>.yaml
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from collections.abc import Generator
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "core"))
sys.path.insert(0, str(_ROOT / "agents"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# Reuse helpers from the generic agent — keep behavior consistent.
from mapping_agent import (  # noqa: E402
    _group_by_table,
    _enrich_column_line,
    _tokenize,
    call_llm,
    load_catalog,
    save_mapping,
)
from agents.agent_utils.mapping_events import MappingEvent, make_event

PROJECT_FILE = _ROOT / "project.yaml"


# ---------------------------------------------------------------------------
# Project loading
# ---------------------------------------------------------------------------

def load_project() -> dict:
    with PROJECT_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_agent_cfg(project: dict) -> dict:
    """Merge `agent_bird` over `agent` so unset keys fall back to the generic block."""
    base = dict(project.get("agent", {}))
    bird = dict(project.get("agent_bird", {}))
    base.update({k: v for k, v in bird.items() if v is not None})
    return base


# ---------------------------------------------------------------------------
# Prompt building (BIRD-grounded)
# ---------------------------------------------------------------------------

_MAX_CONTEXT_LENGTH = 2000


def _col_summary(col: dict) -> str:
    parts = [
        f"{col.get('schema', col.get('source', ''))}."
        f"{col.get('table', '')}."
        f"{col.get('column', col.get('name', ''))}",
        f"[{col.get('data_type', '?')}]",
    ]
    role = col.get("role")
    if role:
        parts.append(f"<{role}>")
    framework = col.get("framework")
    if framework:
        parts.append(f"{{{framework}}}")
    desc = col.get("description") or col.get("table_description")
    if desc:
        parts.append(f"— {desc}")
    return " ".join(parts)


def build_system_prompt(source_name: str, target_name: str) -> str:
    return f"""\
You are a BIRD (Banks' Integrated Reporting Dictionary) mapping expert. Your task
is to find source data from the dataset "{source_name}" that can populate each
column of a BIRD Input Layer (IL) target table in "{target_name}".

BIRD vocabulary (use it precisely):
- Entity / Cube: a table-level concept in the BIRD model.
- Attribute / Variable: a column-level concept.
- Domain / Subdomain: allowed-value or constraint context for an Attribute.
- Member: an allowed value of an enumerated Domain.
- Framework: regulatory collection context (e.g. AnaCredit, FINREP, AE, SHS).
- Reference vs Non-reference: BIRD codification vs original framework codification.

Mapping rules:
- Target ONLY the BIRD Input Layer (IL). Do not propose ELDM/EIL or output-layer mappings.
- You will be given ONE BIRD target table with all its columns.
- You will be given a set of source columns from one or more source tables.
- For EACH target column, find the best-matching source column from ANY of the provided source tables.
- Prefer SEMANTIC match over name similarity. Honor data type and role compatibility.
- Each target column mapping must include source_schema, source_table, and source_column identifying the exact source.
- For each mapping, classify with `transformation_type`:
  * "direct"    — the source column maps 1:1 to the target column with no transformation
                  beyond trivial type coercion.
  * "derived"   — a transformation is required (code translation, unit conversion,
                  concatenation, filtering, computation from multiple fields, etc.).
                  Briefly describe the transformation in `notes`.
  * "unmapped"  — no suitable source column exists; set source_schema, source_table,
                  source_column to null and `confidence` to 0.0.
- target_column must be a plain column name (e.g. "INSTRMNT_ID"), not qualified.
- source_column must be a plain column name (e.g. "loan_id"), not qualified.
- confidence is a float 0.0–1.0 reflecting semantic match strength.
- rationale must be a single concise sentence explaining the match.
- When a column has a "Mapping:" annotation, follow that instruction precisely — it takes priority over \
semantic matching. For example, if a target column says "Mapping: Use GETDATE() function", mark it as \
"derived" with the specified transformation, even if a source column looks like a semantic match.
- After mapping all columns, produce a draft SQL query (SELECT ... FROM ... JOIN ...) that would \
populate the target table from the source data. Use column aliases matching target column names. \
If no columns are mapped, set sql_query to null.
- Respond ONLY with valid JSON — no markdown, no commentary.

Response schema (strict):
{{
  "target_schema": "...",
  "target_table": "...",
  "target_framework": "..." | null,
  "table_confidence": 0.0,
  "table_rationale": "...",
  "sql_query": "SELECT ... FROM ... ;" | null,
  "columns": [
    {{
      "target_column": "...",
      "source_schema": "..." | null,
      "source_table": "..." | null,
      "source_column": "..." | null,
      "confidence": 0.0,
      "rationale": "...",
      "transformation_type": "direct" | "derived" | "unmapped",
      "notes": "..." | null
    }}
  ]
}}
"""


def build_user_prompt(target_table_key: str,
                      target_cols: list[dict],
                      source_columns: list[dict],
                      dataset_context: str = "",
                      source_annotations: dict | None = None,
                      target_annotations: dict | None = None) -> str:
    tgt_lines = "\n".join(_enrich_column_line(c, target_annotations, _col_summary) for c in target_cols)
    src_lines = "\n".join(_enrich_column_line(c, source_annotations, _col_summary) for c in source_columns)

    context_block = ""
    if dataset_context.strip():
        truncated = dataset_context.strip()[:_MAX_CONTEXT_LENGTH]
        context_block = f"\n<dataset_context>\n{truncated}\n</dataset_context>\n"

    return f"""\
{context_block}BIRD IL TARGET TABLE: {target_table_key}
Target columns:
{tgt_lines}

SOURCE COLUMNS (all available — find the best source for each target column):
{src_lines}

For each target column in this BIRD IL table, find the best-matching source column
from any source table. Classify every mapping with `transformation_type` as defined
in the rules. Then produce a SQL query that populates this target table.
"""


# ---------------------------------------------------------------------------
# BIRD-aware source pre-filtering (for each target table)
# ---------------------------------------------------------------------------

def _select_source_tables(tgt_cols: list[dict],
                          source_columns: list[dict],
                          max_tables: int,
                          layer_filter: str | None) -> tuple[list[dict], list[tuple[int, str]]]:
    """Pre-filter source tables to the top-N by combined token + BIRD-context score.

    Returns:
        (filtered_columns, scored_candidates) where scored_candidates is a list
        of (score, table_key) tuples sorted descending by score (top-N selected).

    BIRD additions vs the generic agent:
      - Optional `layer_filter` drops target columns from non-matching layers
        (applied to the target side before scoring, not source).
      - Table score gets bonus when the target column tokens overlap a candidate
        source table's columns based on BIRD `framework` or `role` context from
        the target side.
    """
    if max_tables <= 0 or not source_columns:
        all_tables = sorted({f"{c.get('schema', '')}.{c.get('table', '')}" for c in source_columns})
        return source_columns, [(0, t) for t in all_tables]

    table_cols: dict[str, list[dict]] = {}
    for col in source_columns:
        tbl_key = f"{col.get('schema', '')}.{col.get('table', '')}"
        table_cols.setdefault(tbl_key, []).append(col)

    if len(table_cols) <= max_tables:
        all_tables = sorted(table_cols.keys())
        return source_columns, [(0, t) for t in all_tables]

    tgt_table_name = tgt_cols[0].get("table", "") if tgt_cols else ""
    tgt_table_desc = tgt_cols[0].get("table_description", "") if tgt_cols else ""
    tgt_table_tokens = _tokenize(f"{tgt_table_name} {tgt_table_desc}")

    tgt_col_text = " ".join(
        f"{c.get('column', '')} {c.get('description', '')}"
        for c in tgt_cols
    )
    tgt_col_tokens = _tokenize(tgt_col_text)

    # BIRD context tokens from the target table (framework, role)
    first_tgt = tgt_cols[0] if tgt_cols else {}
    framework = (first_tgt.get("framework") or "").lower()
    roles_text = " ".join(c.get("role", "") or "" for c in tgt_cols)
    bird_tokens = _tokenize(f"{framework} {roles_text}")

    scored: list[tuple[int, str]] = []
    for tbl_key, cols in table_cols.items():
        first = cols[0]
        src_table_name = first.get("table", "")
        src_table_desc = first.get("table_description", "") or ""
        src_table_tokens = _tokenize(f"{src_table_name} {src_table_desc}")
        table_score = len(tgt_table_tokens & src_table_tokens)

        src_col_text = " ".join(
            f"{c.get('column', '')} {c.get('description', '')}"
            for c in cols
        )
        src_col_tokens = _tokenize(src_col_text)
        col_score = len(tgt_col_tokens & src_col_tokens)

        # BIRD bonus: source tokens overlap with target BIRD context.
        bird_bonus = len(src_col_tokens & bird_tokens) + len(src_table_tokens & bird_tokens)

        combined = table_score * 2 + col_score + bird_bonus
        scored.append((combined, tbl_key))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = {tbl_key for _, tbl_key in scored[:max_tables]}
    filtered = [
        col for col in source_columns
        if f"{col.get('schema', '')}.{col.get('table', '')}" in selected
    ]
    return filtered, scored[:max_tables]


# ---------------------------------------------------------------------------
# Main mapping logic
# ---------------------------------------------------------------------------

def _normalize_table_result(result: dict, tgt_cols: list[dict]) -> dict:
    """Ensure new BIRD fields exist on every target table result and column."""
    result.setdefault("status", "pending")
    result.setdefault("target_framework", None)
    result.setdefault("sql_query", None)

    tgt_col_names = [c.get("column", c.get("name")) for c in tgt_cols]
    columns = result.get("columns") or []
    by_tgt = {c.get("target_column"): c for c in columns if isinstance(c, dict)}

    normalized: list[dict] = []
    for tgt_name in tgt_col_names:
        col = by_tgt.get(tgt_name) or {
            "target_column": tgt_name,
            "source_schema": None,
            "source_table": None,
            "source_column": None,
            "confidence": 0.0,
            "rationale": "",
            "transformation_type": "unmapped",
            "notes": None,
        }
        col.setdefault("transformation_type", "unmapped")
        col.setdefault("notes", None)
        col.setdefault("status", "pending")
        # Coerce confidence
        try:
            col["confidence"] = float(col.get("confidence") or 0.0)
        except (TypeError, ValueError):
            col["confidence"] = 0.0
        # Force consistency: unmapped → null source, 0 confidence
        if col.get("source_column") in (None, "", "null"):
            col["source_schema"] = None
            col["source_table"] = None
            col["source_column"] = None
            col["transformation_type"] = "unmapped"
            col["confidence"] = 0.0
        normalized.append(col)

    result["columns"] = normalized
    return result


def map_source_to_bird_stream(
    source_catalog: dict,
    target_catalog: dict,
    agent_cfg: dict,
    dry_run: bool = False,
    dataset_context: str = "",
    target_tables: set[str] | None = None,
    source_annotations: dict | None = None,
    target_annotations: dict | None = None,
) -> Generator[MappingEvent, None, dict]:
    """Generator that yields MappingEvent progress updates while mapping (BIRD variant).

    The final return value (accessible via StopIteration.value) is the
    complete mapping dict.
    """
    source_name = source_catalog["source"]
    target_name = target_catalog["source"]
    provider = agent_cfg.get("provider", "openai")
    model = agent_cfg.get("model", "gpt-4.1")
    temperature = float(agent_cfg.get("temperature", 0))
    api_key_env = agent_cfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")
    layer_filter = agent_cfg.get("layer")  # e.g. "IL"

    if not api_key and not dry_run:
        raise EnvironmentError(
            f"API key not found. Set the '{api_key_env}' environment variable."
        )

    all_target_columns = target_catalog.get("columns", [])
    if layer_filter:
        all_target_columns = [
            c for c in all_target_columns
            if not c.get("layer") or c.get("layer") == layer_filter
        ]
    target_groups = _group_by_table(all_target_columns)
    if target_tables is not None:
        target_groups = {k: v for k, v in target_groups.items() if k in target_tables}
    all_source_columns = source_catalog.get("columns", [])
    max_source_tables = int(agent_cfg.get("max_source_tables", agent_cfg.get("max_target_tables", 0)))
    min_interval = float(agent_cfg.get("min_request_interval", 0))
    system_prompt = build_system_prompt(source_name, target_name)

    total_tables = len(target_groups)
    table_mappings: list[dict] = []
    last_call_time = 0.0

    for idx, (table_key, tgt_cols) in enumerate(target_groups.items(), start=1):
        # --- Step 1: Analyzing source schema ---
        yield make_event(
            "analyzing",
            f"Analyzing source schema ({len(tgt_cols)} columns)",
            target_table=table_key,
            index=idx,
            total=total_tables,
            data={"target_columns": len(tgt_cols)},
        )

        # --- Step 2: Searching for candidate source tables ---
        source_columns, scored_candidates = _select_source_tables(
            tgt_cols, all_source_columns, max_source_tables, layer_filter,
        )
        n_src_tables = len({
            f"{c.get('schema','')}.{c.get('table','')}" for c in source_columns
        })
        candidate_names = [tbl_key for _, tbl_key in scored_candidates[:5]]
        yield make_event(
            "candidates",
            f"Found {n_src_tables} candidates: {', '.join(candidate_names[:3])}{'…' if n_src_tables > 3 else ''}",
            target_table=table_key,
            index=idx,
            total=total_tables,
            data={"source_tables": n_src_tables, "source_columns": len(source_columns), "candidates": candidate_names},
        )

        if dry_run:
            table_result = {
                "target_schema": tgt_cols[0].get("schema"),
                "target_table": tgt_cols[0].get("table"),
                "target_framework": tgt_cols[0].get("framework"),
                "table_confidence": None,
                "table_rationale": "[dry-run]",
                "status": "pending",
                "sql_query": None,
                "columns": [
                    {
                        "target_column": c.get("column", c.get("name")),
                        "source_schema": None,
                        "source_table": None,
                        "source_column": None,
                        "confidence": 0.0,
                        "rationale": "[dry-run]",
                        "transformation_type": "unmapped",
                        "notes": None,
                        "status": "pending",
                    }
                    for c in tgt_cols
                ],
            }
            table_mappings.append(table_result)
            yield make_event(
                "table_done",
                f"[dry-run] {table_key} — 0/{len(tgt_cols)} mapped",
                target_table=table_key,
                index=idx,
                total=total_tables,
                data={"table_confidence": None, "mapped": 0, "unmapped": len(tgt_cols), "high_confidence": 0},
            )
            continue

        # --- Step 3: Scoring table match (via LLM) ---
        user_prompt = build_user_prompt(
            table_key, tgt_cols, source_columns, dataset_context, source_annotations, target_annotations,
        )
        yield make_event(
            "scoring",
            f"Scoring table match via LLM (~{len(user_prompt)} chars)",
            target_table=table_key,
            index=idx,
            total=total_tables,
            data={"prompt_chars": len(user_prompt)},
        )

        try:
            if min_interval > 0:
                elapsed = time.time() - last_call_time
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
            result = call_llm(
                system_prompt, user_prompt, model, api_key, temperature, provider,
            )
            last_call_time = time.time()
            _normalize_table_result(result, tgt_cols)
            table_mappings.append(result)

            # --- Step 4: Emit per-column mapping results ---
            columns_data = []
            for col in result.get("columns", []):
                conf = col.get("confidence", 0.0)
                ttype = col.get("transformation_type", "unmapped")
                src_col = col.get("source_column")
                tgt_col = col.get("target_column", "")
                notes = col.get("notes") or ""
                columns_data.append({
                    "target_column": tgt_col,
                    "source_column": src_col,
                    "confidence": conf,
                    "transformation_type": ttype,
                    "notes": notes,
                })
            yield make_event(
                "columns",
                f"Column-level mapping for {table_key}",
                target_table=table_key,
                index=idx,
                total=total_tables,
                data={"columns": columns_data, "table_confidence": result.get("table_confidence")},
            )

            # --- Step 5: Validating ---
            mapped = sum(1 for c in result.get("columns", []) if c.get("source_column"))
            unmapped = len(result.get("columns", [])) - mapped
            high_conf = sum(1 for c in result.get("columns", []) if (c.get("confidence") or 0) >= 0.8)
            yield make_event(
                "validating",
                f"Validating transformations for {table_key}",
                target_table=table_key,
                index=idx,
                total=total_tables,
            )

            # --- Table complete ---
            yield make_event(
                "table_done",
                f"Complete — {mapped}/{len(result.get('columns', []))} mapped with >{high_conf} at high confidence",
                target_table=table_key,
                index=idx,
                total=total_tables,
                data={
                    "table_confidence": result.get("table_confidence"),
                    "mapped": mapped,
                    "unmapped": unmapped,
                    "high_confidence": high_conf,
                },
            )
        except Exception as exc:
            print(f"    ERROR: {exc}")
            table_mappings.append({
                "target_schema": tgt_cols[0].get("schema"),
                "target_table": tgt_cols[0].get("table"),
                "error": str(exc),
            })
            yield make_event(
                "error",
                f"Error mapping {table_key}: {exc}",
                target_table=table_key,
                index=idx,
                total=total_tables,
                data={"error": str(exc)},
            )

    mapping = {
        "version": 2,
        "agent": "bird",
        "source": source_name,
        "target": target_name,
        "provider": provider,
        "model": model,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "draft",
        "tables": table_mappings,
    }

    yield make_event(
        "done",
        f"Mapping complete: {source_name} \u2192 {target_name} "
        f"({len(table_mappings)} tables)",
        data={"mapping": mapping},
    )

    return mapping


def map_source_to_bird(source_catalog: dict,
                       target_catalog: dict,
                       agent_cfg: dict,
                       dry_run: bool = False,
                       dataset_context: str = "",
                       target_tables: set[str] | None = None,
                       source_annotations: dict | None = None,
                       target_annotations: dict | None = None) -> dict:
    """Run the BIRD mapping agent synchronously (backward-compatible wrapper).

    Exhausts the streaming generator and returns the final mapping dict.
    """
    gen = map_source_to_bird_stream(
        source_catalog, target_catalog, agent_cfg,
        dry_run=dry_run,
        dataset_context=dataset_context,
        target_tables=target_tables,
        source_annotations=source_annotations,
        target_annotations=target_annotations,
    )
    mapping = None
    try:
        while True:
            event = next(gen)
            print(f"  [{event['type']}] {event['message']}")
    except StopIteration as stop:
        mapping = stop.value
    return mapping


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None,
                        help="Source name from project.yaml (default: all)")
    parser.add_argument("--target", default="bird",
                        help="Target name from project.yaml (default: bird)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build prompts and emit stubs without calling the LLM.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = load_project()
    paths = project.get("paths", {})
    source_catalogs_dir = _ROOT / paths.get("source_catalogs", "sources")
    target_catalogs_dir = _ROOT / paths.get("target_catalogs", "targets")
    mappings_dir = _ROOT / paths.get("mappings", "mappings")
    agent_cfg = resolve_agent_cfg(project)

    sources = project.get("sources", [])
    targets = project.get("targets", [])

    if args.source:
        sources = [s for s in sources if s["name"] == args.source]
        if not sources:
            raise SystemExit(f"Source '{args.source}' not found in project.yaml.")
    if args.target:
        targets = [t for t in targets if t["name"] == args.target]
        if not targets:
            raise SystemExit(f"Target '{args.target}' not found in project.yaml.")

    if not sources:
        raise SystemExit("No sources defined in project.yaml.")
    if not targets:
        raise SystemExit("No matching targets defined in project.yaml.")

    for src_cfg in sources:
        for tgt_cfg in targets:
            src_name = src_cfg["name"]
            tgt_name = tgt_cfg["name"]
            print(f"\nBIRD mapping: {src_name} → {tgt_name}")
            try:
                source_catalog = load_catalog(src_name, source_catalogs_dir, kind="source")
                target_catalog = load_catalog(tgt_name, target_catalogs_dir, kind="target")
                mapping = map_source_to_bird(
                    source_catalog, target_catalog, agent_cfg,
                    dry_run=args.dry_run,
                )
                path = save_mapping(src_name, tgt_name, mapping, mappings_dir)
                n_tables = len(mapping["tables"])
                suffix = " [dry-run]" if args.dry_run else ""
                print(f"  -> {path}  ({n_tables} target tables){suffix}")
            except Exception as exc:
                print(f"  ERROR: {exc}")


if __name__ == "__main__":
    main()
