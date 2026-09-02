"""
assessment_agent.py – AI-suggested smart data-quality findings.

Complements the deterministic rule layer in ``core.assessment`` by asking the
project LLM to surface *additional* practical observations from the profile
facts — generic data-quality concerns and regulatory-context flags that the
fixed rules do not cover.

These findings are advisory only. They never block onboarding. The agent is
defensive: any LLM/parse failure returns an empty list so the deterministic
findings are always available.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

_ALLOWED_SEVERITY = {"info", "attention", "high"}
_ALLOWED_CATEGORY = {
    "completeness", "validity", "consistency", "uniqueness",
    "regulatory", "pii", "metadata", "other",
}
_MAX_FINDINGS = 8


def _load_project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the configured LLM and return the raw response text."""
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


_SYSTEM_PROMPT = """You are a data-quality analyst reviewing a single database \
table that is being onboarded for regulatory data mapping (e.g. BIRD/CRDM, CRR3, \
DPM 2.0).

You are given factual profiling statistics already computed from the data. Your \
job is to surface ADDITIONAL practical observations that a human reviewer would \
care about — generic real-world data-quality concerns AND regulatory-context \
flags — that go beyond raw stats.

Strict rules:
- Report only observations that are EVIDENT from the provided facts. Never invent \
numbers or assume values you were not given.
- These are advisory observations, NOT enforced business rules. Do not propose a \
rules engine or block onboarding.
- Do not simply restate a single statistic; add interpretation or a cross-field \
or regulatory insight.
- Prefer quality over quantity. Return at most 8 findings. Return an empty list if \
nothing meaningful stands out.
- Use plain, non-technical language a business analyst can understand.

Respond ONLY with JSON of this exact shape:
{
  "findings": [
    {
      "scope": "dataset" | "column",
      "target": "<table name>" or "<column name>",
      "severity": "info" | "attention" | "high",
      "category": "completeness" | "validity" | "consistency" | "uniqueness" | "regulatory" | "pii" | "metadata" | "other",
      "title": "short title",
      "rationale": "one or two plain-language sentences citing the evident facts",
      "regulatory_note": "optional short regulatory framing, omit if not relevant"
    }
  ]
}
"""


def _build_profile_context(profile: dict[str, Any]) -> str:
    """Build a compact factual summary of the profiled table for the LLM."""
    schema = profile.get("schema_name", "")
    table = profile.get("table_name", "")
    lines = [f"Table: {schema}.{table}"]
    if profile.get("row_count") is not None:
        lines.append(f"Row count: {profile.get('row_count')}")
    if profile.get("primary_key"):
        lines.append(f"Primary key: {', '.join(profile.get('primary_key'))}")
    if profile.get("duplicate_count"):
        lines.append(f"Duplicate PK rows: {profile.get('duplicate_count')}")
    if profile.get("orphan_fk_count"):
        lines.append(f"Orphan foreign keys: {profile.get('orphan_fk_count')}")
    if profile.get("completeness_summary") is not None:
        lines.append(f"Avg completeness: {round(profile['completeness_summary'] * 100, 1)}%")

    lines.append("")
    lines.append("Columns (facts only):")
    for col in profile.get("columns", []) or []:
        name = col.get("name", "?")
        facts = [f"type={col.get('data_type')}"]
        for key, label in (
            ("null_pct", "null"),
            ("distinct_count", "distinct"),
            ("uniqueness_pct", "uniqueness"),
            ("placeholder_count", "placeholders"),
            ("empty_string_count", "empty"),
            ("inferred_pattern", "pattern"),
            ("invalid_format_count", "invalid_format"),
            ("type_mismatch_count", "type_mismatch"),
            ("future_date_count", "future_dates"),
            ("suspicious_date_count", "early_dates"),
            ("numeric_outlier_count", "outliers"),
            ("min_value", "min"),
            ("max_value", "max"),
        ):
            val = col.get(key)
            if val not in (None, 0, []):
                facts.append(f"{label}={val}")
        desc = col.get("description")
        if desc:
            facts.append(f"desc=\"{desc}\"")
        samples = col.get("sample_values") or []
        if samples:
            facts.append("samples=" + ", ".join(str(s) for s in samples[:5]))
        lines.append(f"  - {name}: {', '.join(facts)}")

    return "\n".join(lines)


def _normalize_finding(raw: dict[str, Any], table_name: str) -> dict[str, Any] | None:
    """Validate and coerce one LLM finding into the canonical shape."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title", "")).strip()
    rationale = str(raw.get("rationale", "")).strip()
    if not title or not rationale:
        return None

    scope = raw.get("scope")
    scope = scope if scope in ("dataset", "column") else "column"

    severity = raw.get("severity")
    severity = severity if severity in _ALLOWED_SEVERITY else "info"

    category = raw.get("category")
    category = category if category in _ALLOWED_CATEGORY else "other"

    target = str(raw.get("target") or "").strip() or table_name

    finding = {
        "scope": scope,
        "target": target,
        "severity": severity,
        "category": category,
        "title": title,
        "rationale": rationale,
        "evidence": {},
        "source": "ai",
    }
    reg = raw.get("regulatory_note")
    if reg and str(reg).strip():
        finding["regulatory_note"] = str(reg).strip()
    return finding


def generate_ai_findings(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return AI-suggested findings for a profiled table.

    Always returns a list. On any LLM or parsing failure it returns ``[]`` so
    the caller can still serve the deterministic findings.
    """
    table_name = profile.get("table_name", "")
    context = _build_profile_context(profile)
    user_prompt = (
        f"{context}\n\n"
        "Review the facts above and report additional advisory data-quality "
        "findings as specified."
    )

    try:
        raw = _call_llm(_SYSTEM_PROMPT, user_prompt)
    except Exception:
        return []

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except Exception:
        return []

    items = parsed.get("findings") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return []

    findings: list[dict[str, Any]] = []
    for raw_finding in items[:_MAX_FINDINGS]:
        normalized = _normalize_finding(raw_finding, table_name)
        if normalized:
            findings.append(normalized)
    return findings
