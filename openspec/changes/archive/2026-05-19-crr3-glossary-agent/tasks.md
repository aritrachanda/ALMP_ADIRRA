## 1. Glossary Schema Update

- [x] 1.1 Add `regulatory_context: str = ""` field to `Term` dataclass in `core/glossary.py`
- [x] 1.2 Verify existing glossary.yaml loads correctly with the new field defaulting to empty

## 2. Index Builder Script

- [x] 2.1 Create `crr_indexes/build_index.py` that reads `crr3_index.txt`, splits by separator, filters chunks < 50 chars
- [x] 2.2 Embed valid chunks using Gemini `text-embedding-004` (768d) via `google-genai`
- [x] 2.3 Write new `crr3_index.faiss` (IndexFlatL2, d=768) and print validation stats
- [x] 2.4 Run the build script to regenerate the index

## 3. CRR Retrieval Utility

- [x] 3.1 Create `agents/agent_utils/crr_retrieval.py` with `load_index()` — lazy-loads FAISS index + chunk texts into module globals
- [x] 3.2 Implement `embed_query(text)` — calls Gemini embedding API, returns 768d vector
- [x] 3.3 Implement `search_chunks(query, k=5)` — embeds query, searches FAISS, returns top-k chunks (truncated to 4000 chars) with distances
- [x] 3.4 Implement `lookup_article(article_num)` — loads `crr3_articles.json` + headlines file, returns article text + headline
- [x] 3.5 Add chunk count validation on index load (vectors == valid chunks)

## 4. CRR Agent

- [x] 4.1 Create `agents/crr_agent.py` with LLM prompt construction for regulatory synthesis
- [x] 4.2 Implement `generate_interactive(query)` — search → synthesize → return Term-shaped result
- [x] 4.3 Implement `generate_batch(catalog_name, schema_name)` — iterate columns, skip irrelevant, upsert terms
- [x] 4.4 Add relevance threshold logic to filter low-quality FAISS matches

## 5. Dependencies & Config

- [x] 5.1 Add `faiss-cpu` to `requirements.txt`
- [x] 5.2 Add embedding model config to `project.yaml` if needed (or hardcode for demo)
