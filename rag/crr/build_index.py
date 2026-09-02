"""
build_index.py – Rebuild CRR3 FAISS index using Azure text-embedding-3-large.

Reads crr3_index.txt (chunks separated by ===CHUNK_SEPARATOR===),
filters out tiny chunks, embeds with Azure OpenAI, writes crr3_index.faiss.

Usage:
    python rag/crr/build_index.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

CHUNK_SEPARATOR = "===CHUNK_SEPARATOR==="
MIN_CHUNK_LENGTH = 50
EMBEDDING_DIM = 3072
INDEX_DIR = Path(__file__).resolve().parent  # source data (crr3_index.txt) lives here


def _get_output_dir() -> Path:
    """Resolve RAG cache directory from project.yaml."""
    import yaml
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    rag_cache = project.get("paths", {}).get("rag_cache", "~/.ai-timo/rag/")
    out = Path(rag_cache).expanduser() / "crr"
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_chunks() -> list[str]:
    """Load and filter chunks from crr3_index.txt."""
    txt_path = INDEX_DIR / "crr3_index.txt"
    content = txt_path.read_text(encoding="utf-8")
    raw_chunks = content.split(CHUNK_SEPARATOR)
    valid = [c.strip() for c in raw_chunks if len(c.strip()) > MIN_CHUNK_LENGTH]
    print(f"Loaded {len(raw_chunks)} raw chunks, {len(valid)} valid (>{MIN_CHUNK_LENGTH} chars)")
    return valid


def embed_chunks(chunks: list[str], client, model: str) -> np.ndarray:
    """Embed all chunks using Azure OpenAI embedding model."""
    import time

    vectors = []
    batch_size = 20

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        # Retry with backoff on rate limits
        for attempt in range(6):
            try:
                result = client.embeddings.create(model=model, input=batch)
                for item in result.data:
                    vectors.append(item.embedding)
                break
            except Exception as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    wait = 2 ** attempt * 5  # 5, 10, 20, 40, 80, 160s
                    print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/6)...")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed to embed batch at index {i} after 6 retries")
        print(f"  Embedded {min(i + batch_size, len(chunks))}/{len(chunks)} chunks")
        if i + batch_size < len(chunks):
            time.sleep(1)

    return np.array(vectors, dtype=np.float32)


def build_index(vectors: np.ndarray) -> "faiss.IndexFlatL2":
    """Create a FAISS IndexFlatL2 from the embedding vectors."""
    import faiss

    dim = vectors.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(vectors)
    return index


def main():
    import yaml
    from foundry_client import create_foundry_client

    # Check if index already exists
    output_dir = _get_output_dir()
    faiss_path = output_dir / "crr3_index.faiss"
    if faiss_path.exists():
        answer = input(f"{faiss_path} already exists. Are you sure you want to rebuild? (y/n): ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    # Load config
    project_path = _ROOT / "project.yaml"
    with project_path.open(encoding="utf-8") as f:
        project = yaml.safe_load(f)
    api_key_env = project.get("agent", {}).get("api_key_env", "AZURE_FOUNDRY_KEY")
    embedding_model = project.get("agent", {}).get("embedding_model", "text-embedding-3-large")

    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(f"ERROR: Set {api_key_env} environment variable")
        sys.exit(1)
    if not os.environ.get("AZURE_FOUNDRY_ENDPOINT", ""):
        print("ERROR: Set AZURE_FOUNDRY_ENDPOINT environment variable")
        sys.exit(1)

    client = create_foundry_client(
        api_key=api_key,
        api_key_env=api_key_env,
    )

    # Load and filter chunks
    chunks = load_chunks()

    # Embed
    print(f"\nEmbedding {len(chunks)} chunks with {embedding_model}...")
    vectors = embed_chunks(chunks, client, embedding_model)
    print(f"  Vectors shape: {vectors.shape}")

    assert vectors.shape[1] == EMBEDDING_DIM, f"Expected d={EMBEDDING_DIM}, got d={vectors.shape[1]}"

    # Build and save FAISS index
    index = build_index(vectors)
    output_dir = _get_output_dir()
    out_path = output_dir / "crr3_index.faiss"
    import faiss
    faiss.write_index(index, str(out_path))

    print(f"\nIndex written to: {out_path}")
    print(f"  Dimension: {index.d}")
    print(f"  Vectors:   {index.ntotal}")
    print(f"  Type:      IndexFlatL2")


if __name__ == "__main__":
    main()
