"""AI-assisted semantic-type residual resolver.

This module is imported only when ``include_ai=true``. It is deliberately
 defensive: any provider, parsing, or schema failure returns an empty result so
 the deterministic resolver remains complete on its own.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")


def _load_project() -> dict[str, Any]:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_SAMPLE_ARRAY_KEYS = ("sample_values", "top_values", "code_values")
_EVIDENCE_SAMPLE_KEYS = ("passing", "failing", "refs")


def _apply_sample_policy(
    columns: list[dict[str, Any]], policy: str
) -> list[dict[str, Any]]:
    """Redact raw sample values from residual records before they leave for the LLM.

    Policy (decision D5, default ``masked``):
      - ``full``       — unchanged; send everything (today's behaviour).
      - ``masked``     — replace raw sample arrays with a redaction marker that keeps
                         the count; keep counts/stats/shape metrics.
      - ``stats_only`` — drop sample arrays entirely.
    Unknown values fail safe to ``masked``.
    """
    policy = (policy or "masked").lower()
    if policy == "full":
        return columns
    if policy not in {"masked", "stats_only"}:
        policy = "masked"

    def _scrub(container: dict[str, Any], keys: tuple[str, ...]) -> None:
        for key in keys:
            if key not in container:
                continue
            value = container[key]
            if policy == "stats_only":
                container.pop(key, None)
            else:  # masked
                count = len(value) if isinstance(value, (list, tuple)) else "n/a"
                container[key] = f"<redacted: {count} sample values>"

    safe: list[dict[str, Any]] = []
    for column in columns:
        if not isinstance(column, dict):
            safe.append(column)
            continue
        scrubbed = dict(column)
        _scrub(scrubbed, _SAMPLE_ARRAY_KEYS)
        evidence = scrubbed.get("evidence")
        if isinstance(evidence, list):
            new_evidence = []
            for item in evidence:
                if isinstance(item, dict):
                    item = dict(item)
                    _scrub(item, _EVIDENCE_SAMPLE_KEYS)
                new_evidence.append(item)
            scrubbed["evidence"] = new_evidence
        safe.append(scrubbed)
    return safe


def _call_llm(system_prompt: str, user_prompt: str, project: dict[str, Any] | None = None) -> str:
    from foundry_client import create_foundry_client

    project_cfg = project or _load_project()
    agent_cfg = project_cfg.get("agent", {})
    api_key_env = agent_cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""
    model = agent_cfg.get("model")

    client = create_foundry_client(
        api_key=api_key,
        api_key_env=api_key_env,
    )
    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_prompt + "\n\nRespond with valid JSON.",
        temperature=0,
        text={"format": {"type": "json_object"}},
    )
    return response.output_text.strip()


_SYSTEM_PROMPT = """You resolve residual semantic typing questions for a banking data governance platform.

Rules:
- Use only facts provided in the prompt.
- Choose type_id only from the supplied vocabulary_ids list, or "unresolved".
- Never invent type labels.
- If the type_id is already strongly determined and only a format facet is undecided, do not re-decide the type_id; propose only the format facet.
- Return proposed results only. Do not confirm anything.

Each residual column may include a "governance_context" object with human/curated
meaning that only you can interpret: an approved column Definition, a Business Name,
and a linked Glossary term (title, description, synonyms). Weight these by their
provenance flags:
- Human-authored / steward-approved context (provenance = "human") is STRONG evidence
  of what the column means — prefer it over surface name/value guesses.
- AI-drafted context (provenance = "ai") is WEAK, non-independent corroboration only —
  never treat it as confirmation of your own guess (it may itself be a machine guess).
When a Definition or Glossary term clearly states the meaning, let it drive the type_id
(still only from vocabulary_ids); otherwise fall back to the column's profile evidence.

Return JSON of this shape:
{
  "columns": [
    {
      "key": "source|schema|table|column",
      "type_id": "vocabulary_id_or_unresolved",
      "confidence": 0.0,
      "rationale": "short grounded rationale",
      "evidence_refs": ["facts used"],
      "format": null,
      "format_rationale": null
    }
  ]
}
"""


def resolve_residual_columns(
    *,
    table_context: dict[str, Any],
    residual_columns: list[dict[str, Any]],
    vocabulary_ids: list[str],
    project: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not residual_columns:
        return []
    allowed = set(vocabulary_ids) | {"unresolved"}
    policy = "masked"
    try:
        policy = str((project or _load_project()).get("agent", {}).get("ai_sample_policy", "masked"))
    except Exception:
        policy = "masked"
    safe_columns = _apply_sample_policy(residual_columns, policy)
    prompt = json.dumps(
        {
            "table_context": table_context,
            "vocabulary_ids": vocabulary_ids,
            "residual_columns": safe_columns,
        },
        default=str,
        indent=2,
    )
    try:
        raw = _call_llm(_SYSTEM_PROMPT, prompt, project=project)
        parsed = json.loads(raw)
        columns = parsed.get("columns") or []
        if not isinstance(columns, list):
            return []
        clean: list[dict[str, Any]] = []
        for item in columns:
            if not isinstance(item, dict):
                continue
            type_id = item.get("type_id") or "unresolved"
            if type_id not in allowed:
                type_id = "unresolved"
            clean.append({
                "key": item.get("key"),
                "type_id": type_id,
                "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.0))),
                "rationale": item.get("rationale") or "",
                "evidence_refs": item.get("evidence_refs") or [],
                "format": item.get("format"),
                "format_rationale": item.get("format_rationale"),
            })
        return clean
    except Exception:
        return []
