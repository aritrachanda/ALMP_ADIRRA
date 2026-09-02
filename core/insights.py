"""Smart Data Insights — cross-element hypothesis generation.

generate_hypotheses() reasons *across* a set of findings for a table and
produces root-cause hypotheses and submission readiness signals. AI call is
optional and degrades gracefully to an empty list.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


_SYSTEM_PROMPT = """You are a data quality analyst specialising in EU regulatory \
reporting (AnaCredit, BIRD, COREP, FINREP, DPM 2.0).

You are given a structured list of data-quality findings that were automatically \
detected for a single database table. Your job is to reason ACROSS these findings \
and produce root-cause hypotheses: patterns that explain multiple findings at once \
and are likely to need coordinated remediation.

Rules:
- Only hypothesise about things that are evidently supported by the provided findings.
- Do not invent numbers or statistics not present in the findings.
- Each hypothesis must reference the column names it is based on in "based_on".
- Keep language accessible to a business data steward, not a DBA.
- Return at most 5 hypotheses. Return an empty list if nothing cross-cutting stands out.

Respond ONLY with JSON of this exact shape:
{
  "hypotheses": [
    {
      "title": "short title (max 80 chars)",
      "body": "2-4 sentence explanation of the root cause",
      "recommendation": "1-2 sentence action for the steward",
      "confidence": 0.0,
      "based_on": ["col1", "col2"],
      "sev": "high|attention|info"
    }
  ]
}"""


def _call_llm(findings: list[dict[str, Any]], source: str, table: str,
              agent_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Call the configured LLM and return parsed hypotheses."""
    try:
        from foundry_client import create_foundry_client
    except ImportError:
        return []

    api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
    model = agent_cfg.get("model", "gpt-5.4-mini")

    client = create_foundry_client(
        api_key=api_key,
        api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
    )

    user_prompt = (
        f"Source: {source}\nTable: {table}\n\n"
        f"Findings:\n{json.dumps(findings, indent=2)}\n\n"
        "Respond with valid JSON."
    )

    response = client.responses.create(
        model=model,
        instructions=_SYSTEM_PROMPT,
        input=user_prompt,
        temperature=0,
        text={"format": {"type": "json_object"}},
    )

    raw = response.output_text.strip()
    parsed = json.loads(raw)
    items = parsed.get("hypotheses", [])
    result = []
    for h in items:
        if not isinstance(h, dict):
            continue
        result.append({
            "title": str(h.get("title", ""))[:120],
            "body": str(h.get("body", "")),
            "recommendation": str(h.get("recommendation", "")),
            "confidence": float(h.get("confidence", 0.0)),
            "based_on": [str(c) for c in (h.get("based_on") or [])],
            "sev": h.get("sev", "info") if h.get("sev") in {"high", "attention", "info"} else "info",
        })
    return result[:5]


def generate_hypotheses(
    findings: list[dict[str, Any]],
    source: str,
    table: str,
    agent_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reason across findings and return root-cause hypotheses.

    Returns [] if AI is unavailable or no findings are provided.
    """
    if not findings:
        return []
    try:
        return _call_llm(findings, source, table, agent_cfg)
    except Exception:
        return []
