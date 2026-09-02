"""
dpm_retrieval.py – EBA DPM 2.0 semantic search and table lookup.

Lazy-loads FAISS index + chunk texts on first call. Provides:
  - search_dpm(query, k) – embed query, return top-k DPM datapoint chunks
  - lookup_table(table_code) – return table metadata
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
_INDEX_DIR = _ROOT / "rag" / "dpm"  # fallback / source data


def _get_cache_dir() -> Path:
    """Resolve RAG cache directory from project.yaml."""
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    rag_cache = project.get("paths", {}).get("rag_cache", "~/.ai-timo/rag/")
    return Path(rag_cache).expanduser() / "dpm"

CHUNK_SEPARATOR = "===CHUNK_SEPARATOR==="
MIN_CHUNK_LENGTH = 20
MAX_CHUNK_CHARS = 4000

# Module-level cache (lazy-loaded)
_faiss_index = None
_chunks: list[str] = []
_tables: dict | None = None


def _load_project() -> dict:
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_azure_client():
    """Create a Foundry/OpenAI client using project config."""
    from foundry_client import create_foundry_client

    project = _load_project()
    agent_cfg = project.get("agent", {})
    api_key_env = agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY")
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
        api_key = os.environ.get(api_key_env, "")

    return create_foundry_client(
        api_key=api_key,
        api_key_env=api_key_env,
    )


def _get_embedding_model() -> str:
    project = _load_project()
    return project.get("agent", {}).get("embedding_model", "text-embedding-3-large")


def load_index():
    """Lazy-load FAISS index, chunk texts, and table metadata into module globals."""
    global _faiss_index, _chunks, _tables

    if _faiss_index is not None:
        return

    import faiss

    cache_dir = _get_cache_dir()

    # Load chunks
    txt_path = cache_dir / "dpm_index.txt"
    content = txt_path.read_text(encoding="utf-8")
    raw_chunks = content.split(CHUNK_SEPARATOR)
    _chunks = [c.strip() for c in raw_chunks if len(c.strip()) > MIN_CHUNK_LENGTH]

    # Load FAISS index
    index_path = cache_dir / "dpm_index.faiss"
    _faiss_index = faiss.read_index(str(index_path))

    # Validate alignment
    if _faiss_index.ntotal != len(_chunks):
        raise RuntimeError(
            f"FAISS index has {_faiss_index.ntotal} vectors but found {len(_chunks)} valid chunks. "
            f"Rebuild the index with: python rag/dpm/build_dpm_index.py"
        )

    # Load table metadata
    json_path = cache_dir / "dpm_tables.json"
    with json_path.open(encoding="utf-8") as f:
        _tables = json.load(f)


def embed_query(text: str) -> np.ndarray:
    """Embed a query string using Azure OpenAI, returns a 1-D float32 vector."""
    import time

    client = _get_azure_client()
    model = _get_embedding_model()
    for attempt in range(5):
        try:
            result = client.embeddings.create(model=model, input=[text])
            return np.array(result.data[0].embedding, dtype=np.float32)
        except Exception as exc:
            if attempt < 4 and ("429" in str(exc) or "404" in str(exc) or "rate" in str(exc).lower()):
                time.sleep(2 ** attempt * 2)
            else:
                raise


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _keyword_fallback_search(query: str, k: int = 8, max_distance: float | None = None) -> list[dict]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    scored: list[tuple[float, int]] = []
    for idx, chunk in enumerate(_chunks):
        c_tokens = _tokenize(chunk)
        if not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens)
        if overlap == 0:
            continue
        score = overlap / max(1.0, (len(q_tokens) * len(c_tokens)) ** 0.5)
        if query.lower() in chunk.lower():
            score += 0.2
        score = min(score, 1.0)
        distance = 1.0 - score
        if max_distance is not None and distance > max_distance:
            continue
        scored.append((distance, idx))

    scored.sort(key=lambda x: x[0])
    results: list[dict] = []
    for distance, idx in scored[:k]:
        text = _chunks[idx]
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS]
        results.append({"text": text, "distance": float(distance), "index": int(idx)})
    return results


def search_dpm(query: str, k: int = 8, max_distance: float | None = None) -> list[dict]:
    """Semantic search over DPM 2.0 datapoint chunks.

    Returns list of dicts: {"text": str, "distance": float, "index": int}
    """
    load_index()

    try:
        vec = embed_query(query).reshape(1, -1)
        distances, ids = _faiss_index.search(vec, k)
    except Exception as exc:
        # Gracefully degrade when embedding deployments are unavailable (e.g., 404).
        if "404" in str(exc) or "embedding" in str(exc).lower():
            return _keyword_fallback_search(query=query, k=k, max_distance=max_distance)
        raise

    results = []
    for dist, idx in zip(distances[0], ids[0]):
        if idx < 0:
            continue
        if max_distance is not None and dist > max_distance:
            continue
        text = _chunks[idx]
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS]
        results.append({"text": text, "distance": float(dist), "index": int(idx)})

    return results


def lookup_table(table_code: str) -> Optional[dict]:
    """Look up DPM table metadata by code.

    Returns {"table_code": str, "table_name": str, "group": str, "cell_count": int, "concepts": list}
    or None if not found.
    """
    load_index()

    if _tables is None:
        return None

    meta = _tables.get(table_code)
    if meta is None:
        return None

    return {
        "table_code": table_code,
        "table_name": meta.get("name", ""),
        "group": meta.get("group", ""),
        "cell_count": meta.get("cell_count", 0),
        "concepts": meta.get("concepts", []),
    }


# ---------------------------------------------------------------------------
# Cell-level lookup
# ---------------------------------------------------------------------------

_cells: dict | None = None


def _load_cells():
    """Lazy-load the cell-level lookup JSON."""
    global _cells
    if _cells is not None:
        return
    cache_dir = _get_cache_dir()
    cells_path = cache_dir / "dpm_cells.json"
    if not cells_path.exists():
        _cells = {}
        return
    with cells_path.open(encoding="utf-8") as f:
        _cells = json.load(f)


def lookup_cells(table_code: str, keyword: Optional[str] = None) -> Optional[list[dict]]:
    """Look up cell coordinates for a DPM table, optionally filtered by keyword.

    Args:
        table_code: DPM table code (e.g. 'C_08.01.a')
        keyword: Optional substring to filter datapoints (case-insensitive)

    Returns list of {"row": str, "col": str, "datapoint": str, "cell_ref": str}
    or None if table not found.
    """
    _load_cells()

    if _cells is None:
        return None

    table_cells = _cells.get(table_code)
    if table_cells is None:
        return None

    results = []
    for cell in table_cells:
        if keyword and keyword.lower() not in cell["datapoint"].lower():
            continue
        results.append({
            "row": cell["row"],
            "col": cell["col"],
            "datapoint": cell["datapoint"],
            "cell_ref": f"{{{table_code}, {cell['row']}, {cell['col']}}}",
        })

    return results
