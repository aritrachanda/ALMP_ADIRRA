## Why

The application needs to automatically enrich the business glossary with regulatory context from CRR3 (EU 2024/1623). Currently, glossary terms have business and detailed descriptions but no link to the underlying regulation. A RAG agent can semantically search the CRR3 text and synthesize regulatory definitions, enabling users to understand the legal basis behind banking data concepts like LGD, PD, and CCF.

## What Changes

- New `glossary_agent.py` that uses FAISS semantic search over CRR3 chunks + article K/V lookup to generate regulatory glossary entries
- New `crr_retrieval.py` utility for loading FAISS index, embedding queries with Gemini `text-embedding-004`, and retrieving relevant chunks/articles
- Rebuild existing FAISS index from OpenAI embeddings (d=1536) to Gemini embeddings (d=768) so the project uses a single LLM provider
- Add `regulatory_context` field to the glossary `Term` dataclass for storing CRR3 citations
- New index-building script to regenerate the FAISS index with Gemini embeddings
- Batch mode: iterate target catalog columns, search CRR3, generate regulatory terms
- Interactive mode: user query → semantic search → LLM synthesis → offer to save

## Capabilities

### New Capabilities
- `crr-retrieval`: FAISS index loading, Gemini embedding, semantic search over CRR3 chunks, article lookup by number
- `glossary-agent`: Batch and interactive regulatory glossary generation using RAG over CRR3 text
- `index-builder`: Script to rebuild FAISS index using Gemini text-embedding-004

### Modified Capabilities

## Impact

- `core/glossary.py`: Add `regulatory_context` field to `Term` dataclass
- `agents/`: New `glossary_agent.py` and `agents/agent_utils/crr_retrieval.py`
- `crr_indexes/`: Rebuilt `.faiss` file (d=768 instead of d=1536), same `.txt` and `.json` files
- `requirements.txt`: Add `faiss-cpu`, `google-genai` embedding dependency (already present for LLM)
- `project.yaml`: Potentially add embedding model config
- `ui/pages/glossary.py`: Future integration point (not in this change scope)
