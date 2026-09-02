## ADDED Requirements

### Requirement: Build FAISS index from CRR3 chunks using Gemini embeddings
The system SHALL provide a script that reads `crr3_index.txt`, splits by `===CHUNK_SEPARATOR===`, embeds each valid chunk with Gemini `text-embedding-004`, and writes a new FAISS IndexFlatL2 file.

#### Scenario: Successful index build
- **WHEN** the build script is executed
- **THEN** it reads chunks from `crr3_index.txt`, filters out chunks shorter than 50 characters, embeds remaining chunks, and writes `crr3_index.faiss` with d=768

#### Scenario: Chunk filtering
- **WHEN** chunks are loaded from the text file
- **THEN** chunks with length ≤ 50 characters SHALL be excluded from the index

#### Scenario: Output validation
- **WHEN** the index is written
- **THEN** the script prints the number of vectors stored and the index dimension for verification

### Requirement: Rebuild preserves companion files
The build script SHALL NOT modify `crr3_articles.json`, `articles_headlines_crr3.txt`, or `crr3_index.txt`.

#### Scenario: Only .faiss file is overwritten
- **WHEN** the build script runs
- **THEN** only `crr3_index.faiss` is created/overwritten; all other files in `crr_indexes/` remain unchanged

### Requirement: Consistent chunk ordering
The FAISS vector at index i SHALL correspond to the i-th valid chunk (after filtering) from `crr3_index.txt`, preserving positional alignment.

#### Scenario: ID-to-chunk mapping
- **WHEN** FAISS returns vector ID n
- **THEN** the corresponding text is `valid_chunks[n]` where valid_chunks is the filtered, ordered list from the source file
