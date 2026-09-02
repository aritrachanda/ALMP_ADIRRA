"""
glossary_seeder.py — Scan source/target YAML catalogs and use the configured
LLM to generate candidate Business Glossary terms for every column/concept
that is not already covered.

Usage:
    python core/glossary_seeder.py                         # writes directly to glossary/glossary.yaml
    python core/glossary_seeder.py --dry-run               # prints candidates without writing
    python core/glossary_seeder.py --output candidates.yaml  # save candidates to a review file
    python core/glossary_seeder.py --source banking         # restrict to one source catalog
    python core/glossary_seeder.py --target crdm            # restrict to one target catalog

The script:
  1. Loads all source/target YAML catalogs listed in project.yaml.
  2. Extracts every unique concept (table + column) with any existing description
     and sample values for context.
  3. Compares against all existing glossary terms to skip already-covered concepts.
  4. Sends batches of candidate concepts to the LLM, requesting JSON back.
  5. Merges generated terms into glossary/glossary.yaml via core.glossary.upsert_term.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from core.yaml_cache import load_yaml_cached
sys.path.insert(0, str(_ROOT / "agents"))
from glossary_agent import GlossaryAgent, GlossaryTerm

PROJECT_FILE = _ROOT / "project.yaml"
SOURCES_DIR = _ROOT / "sources" / "generated"
TARGETS_DIR = _ROOT / "targets"

# How many column concepts to include in a single LLM call
BATCH_SIZE = 8

# Minimum seconds between LLM calls
MIN_INTERVAL = 5.0

# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

def _load_project() -> dict:
    return load_yaml_cached(PROJECT_FILE)


def _catalog_path(name: str, kind: str) -> Optional[Path]:
    folder = SOURCES_DIR if kind == "source" else TARGETS_DIR
    p = folder / f"{name}.yaml"
    return p if p.exists() else None


def extract_concepts(catalog: dict, dataset_name: str, kind: str) -> list[dict]:
    """Return a flat list of concept dicts, one per column."""
    concepts = []
    for schema in catalog.get("schemas", []):
        schema_name = schema.get("name", "")
        for table in schema.get("tables", []):
            table_name = table.get("table_name", "")
            table_desc = table.get("description") or ""
            for col in table.get("columns", []):
                col_name = col.get("name", "")
                col_desc = col.get("description") or ""
                samples = col.get("sample_values") or []
                concepts.append({
                    "dataset": dataset_name,
                    "kind": kind,          # "source" | "target"
                    "schema": schema_name,
                    "table": table_name,
                    "table_description": table_desc,
                    "column": col_name,
                    "description": col_desc,
                    "data_type": col.get("data_type", ""),
                    "samples": list(samples)[:5],
                })
    return concepts


# ---------------------------------------------------------------------------
# Concept → human-readable title
# ---------------------------------------------------------------------------

def _to_title(col_name: str) -> str:
    """Convert snake_case / PascalCase / ABBR to a human-readable title."""
    # Split on underscores first
    words = re.sub(r"([A-Z])", r" \1", col_name).replace("_", " ").split()
    return " ".join(w.capitalize() for w in words if w)


# ---------------------------------------------------------------------------
# Gap analysis — skip concepts already in the glossary
# ---------------------------------------------------------------------------

def _existing_titles(agent: GlossaryAgent) -> set[str]:
    return {t.title.lower() for t in agent.all_terms()}


def _is_covered(concept: dict, existing: set[str]) -> bool:
    title = _to_title(concept["column"]).lower()
    col_lower = concept["column"].lower().replace("_", " ")
    return title in existing or col_lower in existing


# ---------------------------------------------------------------------------
# LLM integration (re-uses mapping_agent pattern)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a banking and regulatory-data domain expert helping to build a Business Glossary.

For each concept provided, produce a glossary entry in JSON. The entry must follow this schema exactly:
{
  "title": "Human-readable term name (spell out abbreviations, e.g. LEI → Legal Entity Identifier)",
  "domain": "One of: Banking | Regulatory | Counterparty | Collateral | Lending | General",
  "category": "A finer grouping within the domain, e.g. Identification | Risk | Accounting | Reporting | Address | Classification",
  "business_description": "1-2 sentence non-technical explanation for a business user",
  "detailed_description": "3-5 sentence technical definition referencing data types, regulatory context (e.g. ECB AnaCredit, EBA FINREP, IFRS 9) or calculation logic where relevant",
  "synonyms": ["list", "of", "alternative", "names"],
  "related_objects": ["list", "of", "related", "column", "or", "term", "names"],
  "tags": ["short", "keyword", "tags"]
}

Rules:
- Use clear, plain English. Avoid jargon unless it is explained.
- For regulatory concepts (CRDM, BIRD) reference the relevant regulation if applicable.
- For source banking columns with sample values, use the samples to infer the business meaning.
- Respond ONLY with a valid JSON array — no markdown, no extra text.
"""


def _build_user_prompt(batch: list[dict]) -> str:
    lines = []
    for idx, c in enumerate(batch, 1):
        ctx_parts = []
        if c["table_description"]:
            ctx_parts.append(f"table: {c['table']} ({c['table_description']})")
        else:
            ctx_parts.append(f"table: {c['table']}")
        ctx_parts.append(f"data_type: {c['data_type']}")
        if c["description"]:
            ctx_parts.append(f"existing_description: {c['description']}")
        if c["samples"]:
            ctx_parts.append(f"sample_values: {c['samples']}")
        lines.append(
            f"{idx}. dataset={c['dataset']} ({c['kind']}), "
            f"column={c['column']}, "
            + ", ".join(ctx_parts)
        )
    concepts_block = "\n".join(lines)
    return (
        f"Generate a Business Glossary entry for each of the following "
        f"{len(batch)} banking/regulatory column concepts:\n\n{concepts_block}\n\n"
        "Return a JSON array with one object per concept, in order."
    )


def _call_openai(system: str, user: str, model: str, api_key: str, temperature: float) -> list:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = json.loads(response.choices[0].message.content)
    # Model may wrap the array in a key
    return raw if isinstance(raw, list) else next(iter(raw.values()))


def _call_gemini(system: str, user: str, model: str, api_key: str, temperature: float) -> list:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    raw = json.loads(response.text)
    return raw if isinstance(raw, list) else next(iter(raw.values()))


_PROVIDERS = {"openai": _call_openai, "gemini": _call_gemini}


def call_llm(system: str, user: str, cfg: dict, max_retries: int = 5) -> list:
    provider = cfg["provider"].lower()
    fn = _PROVIDERS.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider '{provider}'")
    api_key = os.environ.get(cfg["api_key_env"], "")
    if not api_key:
        raise RuntimeError(
            f"API key env var '{cfg['api_key_env']}' is not set. "
            "Add it to your .env file."
        )
    for attempt in range(max_retries):
        try:
            return fn(system, user, cfg["model"], api_key, cfg.get("temperature", 0))
        except Exception as exc:
            msg = str(exc)
            is_rate = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate" in msg.lower()
            if is_rate and attempt < max_retries - 1:
                wait = 2 ** attempt * 15
                print(f"  Rate-limited — retrying in {wait}s …")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Term assembly → GlossaryTerm
# ---------------------------------------------------------------------------

import re as _re

def _llm_entry_to_glossary_term(entry: dict) -> GlossaryTerm:
    """Parse an LLM-generated dict into a GlossaryTerm (flat agent schema)."""
    title = (entry.get("title") or "Untitled").strip()
    # Generate a stable id from the title
    term_id = _re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    domain = (entry.get("domain") or "General").strip()
    category = (entry.get("category") or "General").strip()
    return GlossaryTerm(
        id=term_id,
        domain=domain,
        category=category,
        title=title,
        business_description=(entry.get("business_description") or "").strip(),
        detailed_description=(entry.get("detailed_description") or "").strip(),
        synonyms=list(entry.get("synonyms") or []),
        related_objects=list(entry.get("related_objects") or []),
        tags=list(entry.get("tags") or []),
        status="draft",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    source_filter: Optional[str] = None,
    target_filter: Optional[str] = None,
    dry_run: bool = False,
    output_path: Optional[Path] = None,
) -> None:
    project = _load_project()
    agent_cfg = project.get("agent", {})

    # --- Collect all concepts from catalogs ---
    all_concepts: list[dict] = []

    sources = project.get("sources", [])
    for src in sources:
        name = src["name"]
        if source_filter and name != source_filter:
            continue
        p = _catalog_path(name, "source")
        if p is None:
            print(f"  [skip] No source catalog for '{name}' — run catalog_builder.py first.")
            continue
        catalog = load_yaml_cached(p)
        concepts = extract_concepts(catalog, name, "source")
        print(f"  Loaded source '{name}': {len(concepts)} columns")
        all_concepts.extend(concepts)

    targets = project.get("targets", [])
    for tgt in targets:
        name = tgt["name"]
        if target_filter and name != target_filter:
            continue
        p = _catalog_path(name, "target")
        if p is None:
            print(f"  [skip] No target catalog for '{name}'.")
            continue
        catalog = load_yaml_cached(p)
        concepts = extract_concepts(catalog, name, "target")
        print(f"  Loaded target '{name}': {len(concepts)} columns")
        all_concepts.extend(concepts)

    print(f"\nTotal concepts found: {len(all_concepts)}")

    # --- Deduplicate by normalised title (keep first occurrence) ---
    seen: dict[str, dict] = {}
    for c in all_concepts:
        key = _to_title(c["column"]).lower()
        if key not in seen:
            seen[key] = c
    unique_concepts = list(seen.values())
    print(f"Unique concept titles: {len(unique_concepts)}")

    # --- Gap analysis ---
    agent = GlossaryAgent()
    existing = _existing_titles(agent)
    candidates = [c for c in unique_concepts if not _is_covered(c, existing)]
    print(f"Already in glossary: {len(unique_concepts) - len(candidates)}")
    print(f"Candidates to generate: {len(candidates)}")

    if not candidates:
        print("Nothing to do — all concepts are already in the glossary.")
        return

    # --- LLM generation in batches ---
    generated_entries: list[dict] = []
    _last_call = 0.0

    for batch_start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[batch_start : batch_start + BATCH_SIZE]
        print(
            f"\n  Batch {batch_start // BATCH_SIZE + 1} / "
            f"{(len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE} "
            f"({len(batch)} concepts) …"
        )
        for c in batch:
            print(f"    · {c['dataset']}.{c['table']}.{c['column']}")

        # Rate-limit
        elapsed = time.time() - _last_call
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)

        try:
            user_prompt = _build_user_prompt(batch)
            entries = call_llm(_SYSTEM_PROMPT, user_prompt, agent_cfg)
            _last_call = time.time()
            if not isinstance(entries, list):
                print(f"    [warn] Unexpected LLM response type: {type(entries)}")
                continue
            for e in entries:
                print(f"    ✓ {e.get('title', '?')} [{e.get('domain','?')} / {e.get('category','?')}]")
            generated_entries.extend(entries)
        except Exception as exc:
            print(f"    [error] LLM call failed: {exc}")
            continue

    print(f"\nGenerated {len(generated_entries)} entries.")

    if dry_run:
        print("\n--- DRY RUN — not writing to glossary ---")
        print(yaml.dump({"candidates": generated_entries}, default_flow_style=False, allow_unicode=True))
        return

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            yaml.dump(
                {"candidates": generated_entries},
                fh,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        print(f"Candidates saved to: {output_path}")
        return

    # --- Write to glossary.yaml via GlossaryAgent ---
    written = 0
    for entry in generated_entries:
        try:
            term = _llm_entry_to_glossary_term(entry)
            # Skip if id already exists (gap analysis may have missed synonyms)
            if agent.get(term.id):
                print(f"  [skip] '{term.title}' already exists (id={term.id})")
                continue
            agent.add(term)
            written += 1
        except Exception as exc:
            print(f"  [warn] Could not add '{entry.get('title','?')}': {exc}")

    print(f"\nGlossary updated — {written} new terms written to {agent._file}")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scan catalogs and LLM-generate new Business Glossary terms."
    )
    parser.add_argument("--source", default=None, help="Restrict to one source catalog name.")
    parser.add_argument("--target", default=None, help="Restrict to one target catalog name.")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without writing.")
    parser.add_argument(
        "--output",
        default=None,
        help="Save candidates to a YAML review file instead of glossary.yaml.",
    )
    args = parser.parse_args()

    print("=== Glossary Seeder ===")
    run(
        source_filter=args.source,
        target_filter=args.target,
        dry_run=args.dry_run,
        output_path=Path(args.output) if args.output else None,
    )
