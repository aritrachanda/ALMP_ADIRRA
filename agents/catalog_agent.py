"""
catalog_agent.py – AI-powered description generation for data catalog entries.

Generates user_description and mapping_instructions for table columns
using the project's configured LLM. Supports single-column and batch
(all columns in a table) modes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


def _load_project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call LLM and return the response text."""
    from foundry_client import create_foundry_client

    project = _load_project()
    agent_cfg = project.get("agent", {})
    api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
    model = agent_cfg.get("model", "gpt-5.4-mini")

    client = create_foundry_client(
        api_key=api_key,
        api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
    )
    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_prompt + "\n\nRespond with valid JSON.",
        temperature=0,
        text={"format": {"type": "json_object"}},
    )
    return response.output_text.strip()


def _build_table_context(table: dict) -> str:
    """Build a text representation of the table for LLM context."""
    schema_name = table.get("schema_name", "")
    table_name = table.get("table_name", table.get("name", ""))
    pk_cols = table.get("primary_key", [])
    fk_cols = table.get("foreign_keys", [])
    relations = table.get("relations", [])
    row_count = table.get("row_count")
    source_desc = table.get("description") or ""

    lines = [f"Table: {schema_name}.{table_name}"]
    if row_count is not None:
        lines.append(f"Row count: {row_count}")
    if pk_cols:
        lines.append(f"Primary key: {', '.join(pk_cols)}")
    if fk_cols:
        lines.append(f"Foreign keys: {', '.join(fk_cols)}")
    if relations:
        rel_strs = [f"{r['columns']} -> {r['reference_table']}.{r['reference_table_columns']}" for r in relations]
        lines.append(f"Relations: {'; '.join(rel_strs)}")
    if source_desc:
        lines.append(f"Source description: {source_desc}")

    lines.append("")
    lines.append("Columns:")
    for col in table.get("columns", []):
        col_name = col.get("name", "")
        col_type = col.get("data_type", "")
        col_desc = col.get("description") or ""
        distinct = col.get("distinct_count")
        null_pct = col.get("null_pct")
        min_val = col.get("min_value")
        max_val = col.get("max_value")
        samples = col.get("sample_values", [])

        parts = [f"  - {col_name} ({col_type})"]
        if col_name in pk_cols:
            parts.append("[PK]")
        if col_name in fk_cols:
            parts.append("[FK]")
        if distinct is not None:
            parts.append(f"distinct={distinct}")
        if null_pct is not None:
            parts.append(f"null={null_pct:.1%}")
        if min_val is not None:
            parts.append(f"min={min_val}")
        if max_val is not None:
            parts.append(f"max={max_val}")
        if samples:
            parts.append(f"samples=[{', '.join(str(s) for s in samples)}]")
        if col_desc:
            parts.append(f'source_desc="{col_desc}"')
        lines.append(" ".join(parts))

    return "\n".join(lines)


# region Prompt templates

_SYSTEM_DESCRIPTION = """\
You are a data catalog assistant. Generate clear, concise business descriptions \
for database columns. Use the provided statistics and sample values to UNDERSTAND \
the column's purpose, but do NOT cite specific numbers in your output.

Rules:
- Describe the business meaning and purpose of the column
- NEVER mention specific counts, percentages, min/max values, or row counts — \
these change when data is refreshed and do not belong in a description
- DO NOT say things like "800 distinct values", "no nulls", "ranges from X to Y"
- Use sample values to infer meaning (e.g. recognise ISO codes, date formats, \
currency codes) but do not list the samples themselves
- For FK columns, mention the referenced table/relationship
- For low-cardinality columns, note they are categorical or enum-like
- Keep descriptions under 30 words unless more detail is clearly needed
- Output valid JSON only
"""

_SYSTEM_MAPPING = """\
You are a data engineering assistant. Generate technical mapping instructions \
for database columns that would help a data engineer map this column to a \
target data model.

Rules:
- Note the data type and format patterns visible in sample values
- NEVER cite specific counts, percentages, min/max values, or row counts — \
these change when data is refreshed
- DO describe nullability behaviour (e.g. "nullable", "required") and \
whether the column is a natural key or surrogate key
- Note FK relationships and referenced tables
- Mention any transformations or type conversions that might be needed
- Keep instructions concise and actionable
- Output valid JSON only
"""

# endregion


def generate_descriptions(
    table: dict,
    field: str = "user_description",
    column_name: str | None = None,
    user_instructions: str = "",
) -> dict[str, str]:
    """Generate descriptions for columns in a table.

    Args:
        table: The table dict from the catalog (with columns, stats, etc.)
        field: Which annotation field to generate: "user_description" or "mapping_instructions"
        column_name: If set, generate for this column only. Otherwise batch all columns.
        user_instructions: Optional user-provided instructions to guide generation.

    Returns:
        Dict mapping column_name -> generated text.
    """
    context = _build_table_context(table)

    system = _SYSTEM_DESCRIPTION if field == "user_description" else _SYSTEM_MAPPING
    if user_instructions:
        system += f"\n\nAdditional instructions from the user:\n{user_instructions}"

    if column_name:
        user_prompt = (
            f"{context}\n\n"
            f"Generate a {field.replace('_', ' ')} for the column '{column_name}'.\n"
            f'Respond with JSON: {{"{column_name}": "your description"}}'
        )
    else:
        col_names = [c.get("name", "") for c in table.get("columns", [])]
        user_prompt = (
            f"{context}\n\n"
            f"Generate a {field.replace('_', ' ')} for every column in the table.\n"
            f"Respond with JSON: {{{', '.join(f'\"{n}\": \"...\"' for n in col_names)}}}"
        )

    raw = _call_llm(system, user_prompt)

    # Parse JSON from response (strip markdown fences if present)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)
