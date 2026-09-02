"""
crr_agent.py – CRR3 regulatory glossary agent.

Uses FAISS semantic search over CRR3 text to generate regulatory
glossary terms. Two modes:
  - generate_interactive(query) – single query → regulatory answer
  - generate_batch() – enrich glossary terms with CRR3 regulatory context
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "core"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from agents.agent_utils.crr_retrieval import search_chunks, lookup_article

# Relevance threshold: L2 distance above this means the chunk is not relevant
MAX_DISTANCE = 1.6


def _load_project() -> dict:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Call LLM and return parsed JSON response."""
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
        prompt_id="crr_agent._call_llm",
    )
    return json.loads(response.output_text)


def _build_system_prompt() -> str:
    return """\
You are a regulatory knowledge expert specializing in CRR3 (EU Regulation 2024/1623).
Given context from the CRR3 regulation text, synthesize a glossary entry.

Respond ONLY with valid JSON matching this schema:
{
  "title": "Term name",
  "CRR_context": "Per CRR3 Art. X(Y), <concise regulatory definition with article citations>",
  "related_objects": ["Related term 1", "Related term 2"]
}

Rules:
- CRR_context MUST cite specific CRR3 article numbers (e.g., "Art. 4(55)")
- Keep CRR_context concise but complete (1-3 sentences)
- related_objects should list related regulatory concepts mentioned in the same context
- Include relevant regulatory context even if the term is not explicitly defined — e.g. if the term relates to a concept described in an article, cite that article
- Only set CRR_context to "" if the context contains absolutely no relevant regulatory information for the term
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
Detailed Description: {term_context.get('detailed_description', '')}
</term_context>
"""

    return f"""\
<crr3_context>
{context_block}
</crr3_context>
{term_block}
Generate a regulatory glossary entry for: "{query}"
"""


def generate_interactive(query: str, k: int = 8) -> dict | None:
    """Search CRR3 and synthesize a regulatory glossary entry.

    Returns a dict with title, CRR_context, related_objects
    or None if no relevant CRR3 content found.
    """
    chunks = search_chunks(query, k=k, max_distance=MAX_DISTANCE)
    if not chunks:
        return None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, chunks)

    result = _call_llm(system_prompt, user_prompt)

    # Validate result has required fields
    if not result.get("CRR_context"):
        return None

    return {
        "title": result.get("title", query),
        "CRR_context": result["CRR_context"],
        "related_objects": result.get("related_objects", []),
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
    detail_desc = term_dict.get("detailed_description", "")
    synonyms = term_dict.get("synonyms") or []

    # Build search query from title, synonyms, and business description
    parts = [title]
    if synonyms:
        parts.append(", ".join(synonyms))
    if biz_desc:
        parts.append(biz_desc.strip())
    search_query = ". ".join(parts)

    chunks = search_chunks(search_query, k=8, max_distance=MAX_DISTANCE)
    if not chunks:
        print(f"  [{index}/{total}] {title} -> (no CRR3 match)")
        return term_dict, None

    # Build prompt with full term context
    system_prompt = _build_system_prompt()
    term_context = {
        "title": title,
        "business_description": biz_desc,
        "detailed_description": detail_desc,
    }
    user_prompt = _build_user_prompt(title, chunks, term_context=term_context)

    result = _call_llm(system_prompt, user_prompt)

    if result.get("CRR_context"):
        print(f"  [{index}/{total}] {title} -> enriched")
        return term_dict, result
    else:
        print(f"  [{index}/{total}] {title} -> (no relevant definition)")
        return term_dict, None


# Max concurrent API calls (embedding + LLM per term)
_BATCH_CONCURRENCY = 5


def generate_batch(
    domain: str | None = None,
    category: str | None = None,
    force: bool = False,
) -> list[dict]:
    """Enrich existing glossary terms with CRR3 regulatory context.

    Reads terms from glossary.yaml, searches CRR3 for each, and writes
    CRR_context directly back into the existing term entry.
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
        if not force and term_dict.get("CRR_context"):
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
                term_dict["CRR_context"] = result["CRR_context"]
                generated.append(result)

    if generated:
        _save_glossary_yaml(data, glossary_path)
        print(f"\nSaved {len(generated)} regulatory contexts to glossary")

    return generated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CRR3 regulatory glossary agent")
    parser.add_argument("--query", "-q", help="Interactive query mode")
    parser.add_argument("--domain", "-d", help="Batch mode: filter by domain")
    parser.add_argument("--category", "-c", help="Batch mode: filter by category")
    parser.add_argument("--force", "-f", action="store_true", help="Re-enrich terms that already have CRR_context")
    args = parser.parse_args()

    if args.query:
        result = generate_interactive(args.query)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("No relevant CRR3 content found.")
    else:
        generate_batch(domain=args.domain, category=args.category, force=args.force)
