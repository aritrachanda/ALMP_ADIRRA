"""
mapping_agent.py  –  Target-driven AI agent that maps source columns to target columns.

Reads project.yaml to discover sources and targets, loads their catalogs,
then calls an LLM to find source data that populates each target table.
Output is written to mappings/<source>_to_<target>.yaml.

Usage:
        python agents/mapping_agent.py                         # all source→target pairs
        python agents/mapping_agent.py --source banking --target bird
        python agents/mapping_agent.py --source banking --target bird --dry-run

Mapping output structure (version 2, target-centric):

        version: 2
        source: banking
        target: bird
        generated_at: "2026-05-05T12:00:00"
        status: draft
        tables:
            - target_schema: INPUT
                target_table: CNTRPRTS
                table_confidence: 0.95
                table_rationale: Both represent legal entity counterparties.
                status: pending
                sql_query: |
                    SELECT counterparty_id AS CNTRPRTY_ID, name AS NM_ENTTY
                    FROM target.counterparties;
                columns:
                    - target_column: CNTRPRTY_ID
                        source_schema: target
                        source_table: counterparties
                        source_column: counterparty_id
                        confidence: 0.98
                        rationale: Identical semantics — unique counterparty key.
                        transformation_type: direct
                        notes: null
                        status: pending
                    - target_column: NM_ENTTY
                        source_schema: target
                        source_table: counterparties
                        source_column: name
                        confidence: 0.95
                        rationale: NM_ENTTY description is 'Name' which matches name.
                        transformation_type: direct
                        notes: null
                        status: pending
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from collections.abc import Generator
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
PROJECT_FILE = _ROOT / "project.yaml"

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from core.yaml_cache import load_yaml_cached
from agents.agent_utils.mapping_events import MappingEvent, make_event


# ---------------------------------------------------------------------------
# Project / catalog loading
# ---------------------------------------------------------------------------

def load_project() -> dict:
    return load_yaml_cached(PROJECT_FILE)


def load_catalog(name: str, catalogs_dir: Path, kind: str = "source") -> dict:
    """Load a source or target catalog through the shared yaml/postgres dispatch
    (core.catalog.load_catalog_dispatch) -- the same facade every other catalog reader in
    the app already uses, so this agent never reads a stale YAML snapshot while the rest of
    the app is on Postgres. *kind* must be "source" or "target" (matches CatalogSource.kind)."""
    path = catalogs_dir / f"{name}.yaml"
    from core.catalog import load_catalog_dispatch
    catalog = load_catalog_dispatch(path, kind=kind)
    if not catalog:
        raise FileNotFoundError(
            f"Catalog '{path}' not found. Run catalog_builder.py first."
        )
    return catalog


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def _col_summary(col: dict) -> str:
    """One-line text representation of a column for the prompt."""
    parts = [
        f"{col.get('schema', col.get('source', ''))}."
        f"{col.get('table', '')}."
        f"{col.get('column', col.get('name', ''))}",
        f"[{col.get('data_type', '?')}]",
    ]
    desc = col.get("description") or col.get("table_description")
    if desc:
        parts.append(f"— {desc}")
    return " ".join(parts)


def _enrich_column_line(col: dict, annotations: dict | None,
                        col_summary_fn: callable = None) -> str:
    """Return a prompt block for a source column, with annotation sub-lines when available."""
    summary_fn = col_summary_fn or _col_summary
    line = f"  - {summary_fn(col)}"
    if not annotations:
        return line
    schema = col.get("schema", col.get("source", ""))
    table = col.get("table", "")
    col_name = col.get("column", col.get("name", ""))
    tbl_key = f"{schema}.{table}"
    tbl_ann = annotations.get("annotations", {}).get(tbl_key, {})
    col_ann = tbl_ann.get("columns", {}).get(col_name, {})
    sub_lines = []
    user_desc = col_ann.get("user_description")
    if user_desc:
        sub_lines.append(f"    Description: {user_desc}")
    mapping_instr = col_ann.get("mapping_instructions")
    if mapping_instr:
        sub_lines.append(f"    Mapping: {mapping_instr}")
    samples = col.get("sample_values") or []
    if samples:
        sub_lines.append(f"    Samples: {', '.join(str(s) for s in samples)}")
    if sub_lines:
        return line + "\n" + "\n".join(sub_lines)
    return line


def _table_key(col: dict) -> str:
    return f"{col.get('schema', '')}.{col.get('table', '')}"


def _group_by_table(columns: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for col in columns:
        groups.setdefault(_table_key(col), []).append(col)
    return groups


_MAX_CONTEXT_LENGTH = 2000  # characters — cap user-supplied context


def build_system_prompt(source_name: str, target_name: str) -> str:
    return f"""\
You are a data mapping expert. Your task is to find source data from the dataset \
"{source_name}" that can populate each column of a target table in "{target_name}".

Rules:
- You will be given ONE target table with all its columns.
- You will be given a set of source columns from one or more source tables.
- For EACH target column, find the best-matching source column from ANY of the provided source tables.
- Each target column mapping must include source_schema, source_table, and source_column identifying the exact source.
- If no good source match exists for a target column, set source_schema, source_table, source_column to null, \
confidence to 0.0, and transformation_type to "unmapped".
- target_column must be a plain column name (e.g. "INSTRMNT_ID"), not qualified with schema or table.
- source_column must be a plain column name (e.g. "loan_id"), not qualified.
- confidence is a float 0.0–1.0 reflecting semantic similarity.
- rationale must be a single concise sentence explaining the match.
- When a column has a "Mapping:" annotation, follow that instruction precisely — it takes priority over \
semantic matching. For example, if a target column says "Mapping: Use GETDATE() function", mark it as \
"derived" with the specified transformation, even if a source column looks like a semantic match.
- For each mapping, classify with transformation_type:
  * "direct"  — 1:1 mapping with no transformation beyond trivial type coercion.
  * "derived" — a transformation is required (code translation, computation, etc.). Describe in notes.
  * "unmapped" — no suitable source column exists.
- After mapping all columns, produce a draft SQL query (SELECT ... FROM ... JOIN ...) that would \
populate the target table from the source data. Use column aliases matching target column names. \
If no columns are mapped, set sql_query to null. \
Format the SQL query with proper line breaks (\\n) and indentation for readability — each SELECT column \
on its own line, FROM/JOIN/WHERE/GROUP BY each on a new line, and nested subqueries indented.
- Respond ONLY with valid JSON — no markdown, no commentary.

Response schema (strict):
{{
  "target_schema": "...",
  "target_table": "...",
  "table_confidence": 0.0,
  "table_rationale": "...",
  "sql_query": "SELECT\\n  col1 AS target_col1,\\n  col2 AS target_col2\\nFROM source_table\\nJOIN ...;" | null,
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


def build_user_prompt(
    target_table_key: str,
    target_cols: list[dict],
    source_columns: list[dict],
    dataset_context: str = "",
    source_annotations: dict | None = None,
    target_annotations: dict | None = None,
) -> str:
    tgt_lines = "\n".join(_enrich_column_line(c, target_annotations) for c in target_cols)
    src_lines = "\n".join(_enrich_column_line(c, source_annotations) for c in source_columns)

    context_block = ""
    if dataset_context.strip():
        truncated = dataset_context.strip()[:_MAX_CONTEXT_LENGTH]
        context_block = (
            f"\n<dataset_context>\n{truncated}\n</dataset_context>\n"
        )

    return f"""\
{context_block}TARGET TABLE: {target_table_key}
Target columns:
{tgt_lines}

SOURCE COLUMNS (all available — find the best source for each target column):
{src_lines}

For each target column, find the best-matching source column from any source table. \
Then produce a SQL query that populates this target table.
"""


# ---------------------------------------------------------------------------
# LLM call  (provider-dispatched)
# ---------------------------------------------------------------------------

def _call_openai(system_prompt: str, user_prompt: str, model: str, api_key: str, temperature: float) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return json.loads(response.choices[0].message.content)


def _call_gemini(system_prompt: str, user_prompt: str, model: str, api_key: str, temperature: float) -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def _call_azure(system_prompt: str, user_prompt: str, model: str, api_key: str, temperature: float) -> dict:
    import time as _time
    from foundry_client import create_foundry_client

    client = create_foundry_client(api_key=api_key)
    t0 = _time.perf_counter()
    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_prompt + "\n\nRespond with valid JSON.",
        temperature=temperature,
        text={"format": {"type": "json_object"}},
    )
    latency_ms = (_time.perf_counter() - t0) * 1000
    from core.audit.store import record_ai_call
    usage = getattr(response, "usage", None)
    record_ai_call(
        model=model,
        subject_type="mapping",
        subject_id="mapping_agent",
        prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
        completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        latency_ms=latency_ms,
        prompt_id="mapping_agent._call_azure",
    )
    return json.loads(response.output_text)


_PROVIDERS = {
    "openai": _call_openai,
    "gemini": _call_gemini,
    "azure":  _call_azure,
}


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    temperature: float,
    provider: str = "openai",
    max_retries: int = 5,
) -> dict:
    fn = _PROVIDERS.get(provider.lower())
    if fn is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {list(_PROVIDERS)}")
    for attempt in range(max_retries):
        try:
            return fn(system_prompt, user_prompt, model, api_key, temperature)
        except Exception as exc:
            msg = str(exc)
            is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate" in msg.lower()
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2 ** attempt * 15  # 15s, 30s, 60s, 120s …
                print(f"    Rate limited — retrying in {wait}s (attempt {attempt + 1}/{max_retries}) ...")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Source table pre-filtering (for each target table)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Lowercase alpha tokens of length >= 3."""
    import re
    return {t for t in re.findall(r"[a-z]{3,}", text.lower())}


def _select_source_tables(tgt_cols: list[dict], source_columns: list[dict], max_tables: int) -> tuple[list[dict], list[tuple[int, str]]]:
    """Return source columns from up to *max_tables* most relevant source tables for a target table.

    Returns:
        (filtered_columns, scored_candidates) where scored_candidates is a list
        of (score, table_key) tuples sorted descending by score (top-N selected).

    Scoring is two-level:
      1. Table-level: token overlap between target table name + description
         and each source table name + description (weighted 2x).
      2. Column-level: token overlap between all target column names + descriptions
         and all source column names + descriptions.

    The combined score picks the top-N source tables, then returns all columns from those.
    """
    if max_tables <= 0:
        # Return all — build a trivial candidate list
        all_tables = sorted({f"{c.get('schema', '')}.{c.get('table', '')}" for c in source_columns})
        return source_columns, [(0, t) for t in all_tables]

    # Group source columns by table
    table_cols: dict[str, list[dict]] = {}
    for col in source_columns:
        tbl_key = f"{col.get('schema', '')}.{col.get('table', '')}"
        table_cols.setdefault(tbl_key, []).append(col)

    if len(table_cols) <= max_tables:
        all_tables = sorted(table_cols.keys())
        return source_columns, [(0, t) for t in all_tables]

    # Target table-level tokens (table name + description)
    tgt_table_name = tgt_cols[0].get("table", "") if tgt_cols else ""
    tgt_table_desc = tgt_cols[0].get("table_description", "") if tgt_cols else ""
    tgt_table_tokens = _tokenize(f"{tgt_table_name} {tgt_table_desc}")

    # Target column-level tokens (all column names + descriptions)
    tgt_col_text = " ".join(
        f"{c.get('column', '')} {c.get('description', '')}"
        for c in tgt_cols
    )
    tgt_col_tokens = _tokenize(tgt_col_text)

    # Score each source table
    scored = []
    for tbl_key, cols in table_cols.items():
        src_table_name = cols[0].get("table", "")
        src_table_desc = cols[0].get("table_description", "") or ""
        src_table_tokens = _tokenize(f"{src_table_name} {src_table_desc}")
        table_score = len(tgt_table_tokens & src_table_tokens)

        src_col_text = " ".join(
            f"{c.get('column', '')} {c.get('description', '')}"
            for c in cols
        )
        src_col_tokens = _tokenize(src_col_text)
        col_score = len(tgt_col_tokens & src_col_tokens)

        combined = table_score * 2 + col_score
        scored.append((combined, tbl_key))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected_tables = {tbl_key for _, tbl_key in scored[:max_tables]}

    filtered = [col for col in source_columns
                if f"{col.get('schema', '')}.{col.get('table', '')}" in selected_tables]
    return filtered, scored[:max_tables]


# ---------------------------------------------------------------------------
# Main mapping logic (target-driven)
# ---------------------------------------------------------------------------

def map_source_to_target_stream(
    source_catalog: dict,
    target_catalog: dict,
    agent_cfg: dict,
    dry_run: bool = False,
    dataset_context: str = "",
    target_tables: set[str] | None = None,
    source_annotations: dict | None = None,
    target_annotations: dict | None = None,
) -> Generator[MappingEvent, None, dict]:
    """Generator that yields MappingEvent progress updates while mapping.

    The final return value (accessible via StopIteration.value) is the
    complete mapping dict — same shape as map_source_to_target() returns.
    """
    source_name = source_catalog["source"]
    target_name = target_catalog["source"]
    provider = agent_cfg.get("provider", "openai")
    model = agent_cfg.get("model", "gpt-4.1")
    temperature = float(agent_cfg.get("temperature", 0))
    api_key_env = agent_cfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key and not dry_run:
        raise EnvironmentError(
            f"API key not found. Set the '{api_key_env}' environment variable."
        )

    target_groups = _group_by_table(target_catalog.get("columns", []))
    if target_tables is not None:
        target_groups = {
            k: v for k, v in target_groups.items()
            if k in target_tables or k.split(".")[-1] in target_tables
        }
    all_source_columns = source_catalog.get("columns", [])
    max_source_tables = int(agent_cfg.get("max_source_tables", agent_cfg.get("max_target_tables", 0)))  # 0 = no limit
    min_interval = float(agent_cfg.get("min_request_interval", 0))
    system_prompt = build_system_prompt(source_name, target_name)

    total_tables = len(target_groups)
    table_mappings = []
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
        source_columns, scored_candidates = _select_source_tables(tgt_cols, all_source_columns, max_source_tables)
        n_src_tables = len({f"{c.get('schema','')}.{c.get('table','')}" for c in source_columns})
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

        # --- Step 3: Scoring + Step 4: Column mapping (via LLM) ---
        user_prompt = build_user_prompt(table_key, tgt_cols, source_columns, dataset_context, source_annotations, target_annotations)
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
            result = call_llm(system_prompt, user_prompt, model, api_key, temperature, provider)
            last_call_time = time.time()
            result.setdefault("status", "pending")
            for col in result.get("columns", []):
                col.setdefault("status", "pending")
                col.setdefault("transformation_type", "unmapped")
                col.setdefault("notes", None)
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
        f"Mapping complete: {source_name} → {target_name} "
        f"({len(table_mappings)} tables)",
        data={"mapping": mapping},
    )

    return mapping


def map_source_to_target(
    source_catalog: dict,
    target_catalog: dict,
    agent_cfg: dict,
    dry_run: bool = False,
    dataset_context: str = "",
    target_tables: set[str] | None = None,
    source_annotations: dict | None = None,
    target_annotations: dict | None = None,
) -> dict:
    """Run the mapping agent synchronously (backward-compatible wrapper).

    Exhausts the streaming generator and returns the final mapping dict.
    """
    gen = map_source_to_target_stream(
        source_catalog, target_catalog, agent_cfg,
        dry_run=dry_run,
        dataset_context=dataset_context,
        target_tables=target_tables,
        source_annotations=source_annotations,
        target_annotations=target_annotations,
    )
    # Exhaust the generator; the return value is in StopIteration.value
    mapping = None
    try:
        while True:
            event = next(gen)
            # Print progress for CLI usage
            print(f"  [{event['type']}] {event['message']}")
    except StopIteration as stop:
        mapping = stop.value
    return mapping


def save_mapping(source_name: str, target_name: str, mapping: dict, mappings_dir: Path) -> Path:
    """Save mapping to YAML, merging new tables into any existing file.

    Tables in the new mapping replace same-named tables in the existing file;
    tables that were not part of this run are preserved unchanged.
    """
    mappings_dir.mkdir(parents=True, exist_ok=True)
    out_path = mappings_dir / f"{source_name}_to_{target_name}.yaml"

    # Load existing mapping if present
    existing: dict | None = None
    if out_path.exists():
        with out_path.open(encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or None

    if existing and isinstance(existing.get("tables"), list):
        # Build lookup of new tables by (target_schema, target_table) key
        new_table_keys: set[tuple[str, str]] = set()
        for t in mapping.get("tables", []):
            new_table_keys.add((t.get("target_schema", ""), t.get("target_table", "")))

        # Keep existing tables that are NOT being replaced
        merged_tables = [
            t for t in existing["tables"]
            if (t.get("target_schema", ""), t.get("target_table", "")) not in new_table_keys
        ]
        # Append all new tables
        merged_tables.extend(mapping.get("tables", []))

        # Use the new mapping metadata but with merged tables
        mapping = {**mapping, "tables": merged_tables}

    with out_path.open("w", encoding="utf-8") as fh:
        yaml.dump(mapping, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI agent: map source columns to target columns using an LLM."
    )
    parser.add_argument("--source", default=None, help="Source name from project.yaml")
    parser.add_argument("--target", default=None, help="Target name from project.yaml")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build prompts and output stubs without calling the LLM.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = load_project()
    paths = project.get("paths", {})
    source_catalogs_dir = _ROOT / paths.get("source_catalogs", paths.get("catalogs", "sources"))
    target_catalogs_dir = _ROOT / paths.get("target_catalogs", paths.get("catalogs", "targets"))
    mappings_dir = _ROOT / paths.get("mappings", "mappings")
    agent_cfg = project.get("agent", {})

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
        raise SystemExit("No targets defined in project.yaml.")

    for src_cfg in sources:
        for tgt_cfg in targets:
            src_name = src_cfg["name"]
            tgt_name = tgt_cfg["name"]
            print(f"\nMapping: {src_name} → {tgt_name}")

            try:
                source_catalog = load_catalog(src_name, source_catalogs_dir, kind="source")
                target_catalog = load_catalog(tgt_name, target_catalogs_dir, kind="target")
                mapping = map_source_to_target(
                    source_catalog, target_catalog, agent_cfg,
                    dry_run=args.dry_run,
                )
                path = save_mapping(src_name, tgt_name, mapping, mappings_dir)
                n_tables = len(mapping["tables"])
                n_cols = sum(len(t.get("columns", [])) for t in mapping["tables"])
                suffix = " [dry-run]" if args.dry_run else ""
                print(f"  -> {path}  ({n_tables} target tables, {n_cols} columns){suffix}")
            except Exception as exc:
                print(f"  ERROR: {exc}")


if __name__ == "__main__":
    main()
