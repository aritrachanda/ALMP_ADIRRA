"""
build_dpm_index.py – Build FAISS index over EBA DPM 2.0 datapoints.

Parses dpm2.0.yaml, formats each cell into a searchable chunk string
(with table group, table name, cell coordinate, and datapoint path),
embeds all chunks using Azure OpenAI text-embedding-3-large, and writes:
  - dpm_index.faiss  (FAISS IndexFlatL2)
  - dpm_index.txt    (chunk texts separated by ===CHUNK_SEPARATOR===)
  - dpm_tables.json  (table metadata for lookup)

Usage:
    python rag/dpm/build_dpm_index.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# Resolve output directory from project.yaml paths.rag_cache (expands ~)
def _get_output_dir() -> Path:
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    rag_cache = project.get("paths", {}).get("rag_cache", "~/.ai-timo/rag/")
    out = Path(rag_cache).expanduser() / "dpm"
    out.mkdir(parents=True, exist_ok=True)
    return out

INDEX_DIR = Path(__file__).resolve().parent  # source data (dpm2.0.yaml) lives here
OUTPUT_DIR = _get_output_dir()
DPM_YAML = INDEX_DIR / "dpm2.0.yaml"
CHUNK_SEPARATOR = "===CHUNK_SEPARATOR==="
EMBEDDING_DIM = 3072


# ---------------------------------------------------------------------------
# Parse DPM YAML
# ---------------------------------------------------------------------------

def parse_dpm(yaml_path: Path) -> tuple[list[str], dict]:
    """Parse dpm2.0.yaml and return (chunks, table_metadata).

    Each chunk is a formatted string:
        Group: <group_name>
        Table: <table_code> - <table_name>
        Cell: {table_code, row, col}
        Datapoint: <pipe-separated items>

    table_metadata: {table_code: {name, group, cell_count, concepts[]}}
    """
    print(f"Parsing {yaml_path}...")
    with yaml_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    current_group = ""
    current_table_code = ""
    current_table_name = ""

    chunks: list[str] = []
    seen_chunks: set[str] = set()
    table_meta: dict[str, dict] = {}

    current_cell_coord = ""

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("table_group_name:"):
            current_group = stripped.split(":", 1)[1].strip()

        elif stripped.startswith("- table_code:"):
            current_table_code = stripped.split(":", 1)[1].strip()
            if current_table_code not in table_meta:
                table_meta[current_table_code] = {
                    "name": "",
                    "group": current_group,
                    "cell_count": 0,
                    "concepts": set(),
                }

        elif stripped.startswith("table_name:"):
            current_table_name = stripped.split(":", 1)[1].strip()
            if current_table_code in table_meta:
                table_meta[current_table_code]["name"] = current_table_name
                table_meta[current_table_code]["group"] = current_group

        elif re.match(r"\{.+?,\s*r[\d*]+,\s*c\d+\}", stripped):
            # Cell coordinate line, e.g. "{C_08.01.a, r0010, c0060}:"
            current_cell_coord = stripped.rstrip(":")

        elif "- items:" in stripped and current_table_code:
            match = re.search(r"\[(.+?)\]", stripped)
            if not match:
                continue

            items_path = match.group(1).strip()

            chunk = (
                f"Group: {current_group}\n"
                f"Table: {current_table_code} - {current_table_name}\n"
                f"Cell: {current_cell_coord}\n"
                f"Datapoint: {items_path}"
            )

            # Deduplicate identical chunks
            if chunk not in seen_chunks:
                seen_chunks.add(chunk)
                chunks.append(chunk)

            # Update table metadata
            meta = table_meta[current_table_code]
            meta["cell_count"] += 1
            parts = [p.strip() for p in items_path.split("|")]
            for p in parts:
                meta["concepts"].add(p)

    # Convert concept sets to sorted lists for JSON serialization
    for code in table_meta:
        table_meta[code]["concepts"] = sorted(table_meta[code]["concepts"])

    print(f"  Total cells: {sum(m['cell_count'] for m in table_meta.values())}")
    print(f"  Unique chunks: {len(chunks)}")
    print(f"  Tables: {len(table_meta)}")

    return chunks, table_meta


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def get_azure_client():
    """Create a Foundry/OpenAI client using project config."""
    from foundry_client import create_foundry_client

    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)

    agent_cfg = project.get("agent", {})
    api_key_env = agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY")
    api_key = os.environ.get(api_key_env, "")

    return create_foundry_client(
        api_key=api_key,
        api_key_env=api_key_env,
    )


def get_embedding_model() -> str:
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    return project.get("agent", {}).get("embedding_model", "text-embedding-3-large")


def embed_chunks(chunks: list[str], client, model: str) -> np.ndarray:
    """Embed all chunks using Azure OpenAI embedding model."""
    vectors = []
    batch_size = 100
    total_batches = (len(chunks) + batch_size - 1) // batch_size

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        for attempt in range(6):
            try:
                result = client.embeddings.create(model=model, input=batch)
                for item in result.data:
                    vectors.append(item.embedding)
                break
            except Exception as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    wait = 2 ** attempt * 5
                    print(f"  Rate limited on batch {batch_num}, waiting {wait}s (attempt {attempt + 1}/6)...")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed to embed batch {batch_num} after 6 retries")

        if batch_num % 10 == 0 or batch_num == total_batches:
            print(f"  Embedded {min(i + batch_size, len(chunks))}/{len(chunks)} chunks ({batch_num}/{total_batches} batches)")

    return np.array(vectors, dtype=np.float32)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Check if index already exists
    faiss_path = OUTPUT_DIR / "dpm_index.faiss"
    if faiss_path.exists():
        answer = input(f"{faiss_path} already exists. Are you sure you want to rebuild? (y/n): ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    # 1. Parse DPM YAML
    chunks, table_meta = parse_dpm(DPM_YAML)

    # 2. Write chunk texts
    txt_path = OUTPUT_DIR / "dpm_index.txt"
    print(f"Writing {len(chunks)} chunks to {txt_path}...")
    txt_path.write_text(
        CHUNK_SEPARATOR.join(chunks),
        encoding="utf-8",
    )

    # 3. Write table metadata JSON
    json_path = OUTPUT_DIR / "dpm_tables.json"
    print(f"Writing table metadata to {json_path}...")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(table_meta, f, indent=2, ensure_ascii=False)

    # 4. Embed chunks
    print("Embedding chunks...")
    client = get_azure_client()
    model = get_embedding_model()
    vectors = embed_chunks(chunks, client, model)
    print(f"  Vectors shape: {vectors.shape}")

    # 5. Build and write FAISS index
    import faiss

    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)

    faiss_path = OUTPUT_DIR / "dpm_index.faiss"
    print(f"Writing FAISS index to {faiss_path}...")
    faiss.write_index(index, str(faiss_path))

    print(f"\nDone! Index has {index.ntotal} vectors ({vectors.shape[1]}-dim).")
    print(f"  {faiss_path.name}: {faiss_path.stat().st_size / 1024 / 1024:.0f} MB")
    print(f"  {txt_path.name}: {txt_path.stat().st_size / 1024 / 1024:.0f} MB")


if __name__ == "__main__":
    main()
