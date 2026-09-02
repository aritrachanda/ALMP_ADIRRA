"""
dpm_agent.py – EBA DPM 2.0 glossary enrichment agent.

Uses FAISS semantic search over DPM 2.0 datapoints to generate reporting
context for glossary terms. Two modes:
  - generate_interactive(query) – single query → DPM context with table/cell refs
  - generate_batch() – enrich glossary terms with DPM reporting context
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from agents.agent_utils.dpm_retrieval import search_dpm

# Relevance threshold: L2 distance above this means the chunk is not relevant
MAX_DISTANCE = 1.6


def _load_project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Call LLM and return parsed JSON response."""
    import time
    from foundry_client import create_foundry_client

    project = _load_project()
    agent_cfg = project.get("agent", {})
    api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
    model = agent_cfg.get("model", "gpt-5.4-mini")

    client = create_foundry_client(
        api_key=api_key,
        api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
    )
    t0 = time.perf_counter()
    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_prompt + "\n\nRespond with valid JSON.",
        temperature=0,
        text={"format": {"type": "json_object"}},
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    from core.audit.store import record_ai_call
    usage = getattr(response, "usage", None)
    record_ai_call(
        model=model,
        subject_type="regulation_lookup",
        subject_id=user_prompt[:120],
        prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
        completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        latency_ms=latency_ms,
        prompt_id="dpm_agent._call_llm",
    )
    return json.loads(response.output_text)


def _build_system_prompt() -> str:
    return """\
You are a regulatory reporting expert specializing in EBA DPM 2.0 (Data Point Model).
Given context from DPM datapoint search results, synthesize a reporting context entry.

Respond ONLY with valid JSON matching this schema:
{
  "title": "Term name",
  "DPM_context": "Concise reporting context with table codes and cell references",
  "related_tables": ["C_08.01.a", "C_09.02"]
}

Rules:
- DPM_context MUST cite specific DPM table codes (e.g., "C_08.01.a")
- Include cell references in format {table_code, row, col} when available in the context
- Keep DPM_context concise (2-4 sentences) listing the most relevant reporting templates
- related_tables lists all DPM table codes mentioned
- Only set DPM_context to "" if the context contains absolutely no relevant DPM reporting information
- Focus on WHERE the concept is reported (which templates/cells), not definitions
"""


def _build_user_prompt(query: str, chunks: list[dict], term_context: dict | None = None) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Chunk {i}, distance={chunk['distance']:.3f}]\n{chunk['text']}")
    context_block = "\n\n---\n\n".join(context_parts)

    term_block = ""
    if term_context:
        term_block = f"""
<term_context>
Title: {term_context.get('title', '')}
Business Description: {term_context.get('business_description', '')}
</term_context>
"""

    return f"""\
<dpm_context>
{context_block}
</dpm_context>
{term_block}
Generate a DPM reporting context entry for: "{query}"
"""


def generate_interactive(query: str, k: int = 8) -> dict | None:
    """Search DPM 2.0 and synthesize a reporting context entry.

    Returns a dict with title, DPM_context, related_tables
    or None if no relevant DPM content found.
    """
    chunks = search_dpm(query, k=k, max_distance=MAX_DISTANCE)
    if not chunks:
        return None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, chunks)

    result = _call_llm(system_prompt, user_prompt)

    if not result.get("DPM_context"):
        return None

    return {
        "title": result.get("title", query),
        "DPM_context": result["DPM_context"],
        "related_tables": result.get("related_tables", []),
    }


def _load_glossary_yaml() -> tuple[dict, Path]:
    """Load the full glossary YAML and return (data, path)."""
    glossary_path = _ROOT / "glossary" / "glossary.yaml"
    with glossary_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data, glossary_path


def _save_glossary_yaml(data: dict, path: Path) -> None:
    """Save the glossary YAML back to disk."""
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _enrich_single_term(term_dict: dict, index: int, total: int) -> tuple[dict, dict | None]:
    """Enrich a single term. Returns (term_dict, result) or (term_dict, None)."""
    title = term_dict.get("title", "")
    biz_desc = term_dict.get("business_description", "")
    synonyms = term_dict.get("synonyms") or []

    # Build search query from title, synonyms, and business description
    parts = [title]
    if synonyms:
        parts.append(", ".join(synonyms))
    if biz_desc:
        parts.append(biz_desc.strip())
    search_query = ". ".join(parts)

    chunks = search_dpm(search_query, k=8, max_distance=MAX_DISTANCE)
    if not chunks:
        print(f"  [{index}/{total}] {title} -> (no DPM match)")
        return term_dict, None

    system_prompt = _build_system_prompt()
    term_context = {
        "title": title,
        "business_description": biz_desc,
    }
    user_prompt = _build_user_prompt(title, chunks, term_context=term_context)

    result = _call_llm(system_prompt, user_prompt)

    if result.get("DPM_context"):
        print(f"  [{index}/{total}] {title} -> enriched")
        return term_dict, result
    else:
        print(f"  [{index}/{total}] {title} -> (no relevant DPM context)")
        return term_dict, None


# Max concurrent API calls (embedding + LLM per term)
_BATCH_CONCURRENCY = 5


def generate_batch(
    domain: str | None = None,
    category: str | None = None,
    force: bool = False,
) -> list[dict]:
    """Enrich existing glossary terms with DPM reporting context.

    Reads terms from glossary.yaml, searches DPM for each, and writes
    DPM_context directly back into the existing term entry.
    Does NOT create new entries. Skips already-enriched terms unless force=True.

    Uses thread-pool concurrency for faster processing.

    Returns list of enriched results.
    """
    data, glossary_path = _load_glossary_yaml()
    all_terms = data.get("terms", [])

    # Filter terms to process
    terms_to_process = []
    for term_dict in all_terms:
        if domain and term_dict.get("domain", "").lower() != domain.lower():
            continue
        if category and term_dict.get("category", "").lower() != category.lower():
            continue
        if not force and term_dict.get("DPM_context"):
            continue
        terms_to_process.append(term_dict)

    total = len(terms_to_process)
    print(f"Processing {total} glossary terms" +
          (f" (domain={domain})" if domain else "") +
          (f" (category={category})" if category else "") +
          f" (concurrency={_BATCH_CONCURRENCY})")

    generated = []

    with ThreadPoolExecutor(max_workers=_BATCH_CONCURRENCY) as executor:
        futures = {
            executor.submit(_enrich_single_term, term_dict, i, total): term_dict
            for i, term_dict in enumerate(terms_to_process, 1)
        }
        for future in as_completed(futures):
            term_dict, result = future.result()
            if result:
                term_dict["DPM_context"] = result["DPM_context"]
                generated.append(result)

    if generated:
        _save_glossary_yaml(data, glossary_path)
        print(f"\nSaved {len(generated)} DPM contexts to glossary")

    return generated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DPM glossary enrichment")
    parser.add_argument("--domain", help="Filter by domain")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--force", action="store_true", help="Re-enrich already enriched terms")
    parser.add_argument("--query", help="Interactive mode: single query")
    args = parser.parse_args()

    if args.query:
        result = generate_interactive(args.query)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("No relevant DPM content found.")
    else:
        results = generate_batch(domain=args.domain, category=args.category, force=args.force)
        print(f"\nTotal enriched: {len(results)}")
