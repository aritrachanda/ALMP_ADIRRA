"""
crr_retrieval.py – CRR3 semantic search and article lookup.

Lazy-loads FAISS index + chunk texts on first call. Provides:
  - search_chunks(query, k) – embed query, return top-k CRR3 chunks
  - lookup_article(num) – direct article text + headline lookup
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
_INDEX_DIR = _ROOT / "rag" / "crr"  # source data (crr3_index.txt, articles) lives here

CHUNK_SEPARATOR = "===CHUNK_SEPARATOR==="
MIN_CHUNK_LENGTH = 50
MAX_CHUNK_CHARS = 4000

# Module-level cache (lazy-loaded)
_faiss_index = None
_chunks: list[str] = []
_articles: dict | None = None
_headlines: dict[str, str] = {}


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


def _get_cache_dir() -> Path:
    """Resolve RAG cache directory from project.yaml."""
    project = _load_project()
    rag_cache = project.get("paths", {}).get("rag_cache", "~/.ai-timo/rag/")
    return Path(rag_cache).expanduser() / "crr"


def _get_embedding_model() -> str:
    project = _load_project()
    return project.get("agent", {}).get("embedding_model", "text-embedding-3-large")


def load_index():
    """Lazy-load FAISS index and chunk texts into module globals."""
    global _faiss_index, _chunks

    if _faiss_index is not None:
        return

    import faiss

    cache_dir = _get_cache_dir()

    # Load chunks (source text stays in repo)
    txt_path = _INDEX_DIR / "crr3_index.txt"
    content = txt_path.read_text(encoding="utf-8")
    raw_chunks = content.split(CHUNK_SEPARATOR)
    _chunks = [c.strip() for c in raw_chunks if len(c.strip()) > MIN_CHUNK_LENGTH]

    # Load FAISS index from cache
    index_path = cache_dir / "crr3_index.faiss"
    _faiss_index = faiss.read_index(str(index_path))

    # Validate alignment
    if _faiss_index.ntotal != len(_chunks):
        raise RuntimeError(
            f"FAISS index has {_faiss_index.ntotal} vectors but found {len(_chunks)} valid chunks. "
            f"Rebuild the index with: python rag/crr/build_index.py"
        )


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


def _keyword_fallback_search(query: str, k: int = 5, max_distance: float | None = None) -> list[dict]:
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
        results.append({"text": text, "distance": float(distance), "chunk_id": int(idx)})
    return results


def search_chunks(query: str, k: int = 5, max_distance: float | None = None) -> list[dict]:
    """Semantic search over CRR3 chunks.

    Returns list of dicts: {"text": str, "distance": float, "chunk_id": int}
    Chunks are truncated to MAX_CHUNK_CHARS.
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
        results.append({"text": text, "distance": float(dist), "chunk_id": int(idx)})

    return results


def _load_articles():
    """Lazy-load articles JSON and headlines."""
    global _articles, _headlines

    if _articles is not None:
        return

    articles_path = _INDEX_DIR / "crr3_articles.json"
    with articles_path.open(encoding="utf-8") as f:
        _articles = json.load(f)

    headlines_path = _INDEX_DIR / "articles_headlines_crr3.txt"
    _headlines = {}
    if headlines_path.exists():
        text = headlines_path.read_text(encoding="utf-16")
        for line in text.splitlines():
            if ":" in line:
                # "Article 5a: Definitions specific to crypto-assets"
                prefix, headline = line.split(":", 1)
                num = prefix.replace("Article", "").strip()
                _headlines[num] = headline.strip()


def lookup_article(article_num: str) -> Optional[dict]:
    """Look up a CRR3 article by number.

    Returns {"text": str, "headline": str, "article_num": str} or None.
    """
    _load_articles()

    texts = _articles.get(article_num)
    if texts is None:
        return None

    full_text = "\n\n".join(texts)
    headline = _headlines.get(article_num, "")

    return {
        "text": full_text,
        "headline": headline,
        "article_num": article_num,
    }
