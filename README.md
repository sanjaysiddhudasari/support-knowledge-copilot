# Support Knowledge Copilot

A RAG-based support knowledge assistant with multi-format document ingestion (Markdown, TXT, PDF, DOCX, HTML), hybrid retrieval, access control, document versioning, freshness-aware retrieval, and verified citations.

## Architecture

- **Frontend:** Streamlit
- **API:** FastAPI
- **Vector store:** Qdrant Cloud
- **Deployed embeddings:** Qdrant Cloud Inference using `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Lexical retrieval:** BM25 index stored in `data/bm25/index.joblib`
- **Hybrid retrieval:** Reciprocal Rank Fusion (RRF), used as the production default
- **Reranking:** Cross-Encoder is supported for local/evaluation workflows but disabled by default in production to avoid its additional memory footprint
- **Generation + citation verification:** DeepSeek
- **Authentication + user profiles:** Supabase Auth + Supabase Postgres
- **Access levels:** public, internal, admin
- **Ingestion:** format-dispatching loaders (`app/ingestion/`) for MD, TXT, PDF, DOCX and HTML with deterministic chunk IDs and incremental indexing

## Document ingestion

Supported formats:

| Format | Extensions | Extraction | Chunking |
|---|---|---|---|
| Markdown | `.md` | UTF-8 + optional YAML front matter | heading-aware (`#`–`###`) |
| Plain text | `.txt` | UTF-8 | generic paragraph chunking |
| PDF | `.pdf` | pypdf, text layer per page | page-aware + generic |
| Word | `.docx` | python-docx, paragraph text | heading-aware when headings exist, otherwise generic |
| HTML | `.html`, `.htm` | BeautifulSoup visible text | heading-aware (`h1`–`h3`) |

```text
document → loader (format dispatch) → LoadedDocument → chunk_document() → list[Chunk]
        → Qdrant (Cloud Inference) + BM25 → hybrid RRF retrieval
```

- Loaders live in `app/ingestion/loader.py`. The indexer never parses a format
  itself — it asks the loader layer for a normalized `LoadedDocument`.
- `SUPPORTED_EXTENSIONS` is owned by the ingestion layer and reused by the
  indexer for discovery, so new/modified/unchanged/deleted detection works for
  every format. Content hashes are always computed over the raw file bytes.
- Chunk IDs remain deterministic: `{filename}_chunk_{n}`, numbered from 1 in
  document order. The same unchanged file always produces the same IDs.
- Markdown metadata is unchanged (front matter unchanged). Non-Markdown formats
  use the existing metadata defaults. `file_type` and `page` are additive,
  optional chunk/Qdrant payload fields — the ACL fields are untouched.
- `app/ingestion/frontmatter.py` holds the shared front-matter parser;
  `app/ingestion/chunker.py` holds the shared section/text/page chunkers.

### Upload support

The admin upload endpoint (`POST /api/documents`) and the Streamlit sidebar
accept MD, TXT, PDF, DOCX and HTML. The backend validates the extension
independently of the UI, enforces a 20 MB size limit, and rejects unparsable
files before indexing. Uploaded content is never executed.

### Limitations

- Scanned / image-only PDFs are not supported: a PDF with no extractable text
  returns a clear error (OCR is out of scope for this phase).
- Embedded images are not extracted from any format.
- HTML JavaScript is never executed — only visible text is indexed, and
  `<script>`, `<style>` and `<noscript>` are stripped before chunking.
- DOCX tables and images are not extracted; paragraph text only.
- XLSX, PPTX, CSV and EPUB are not currently supported.
- No LangChain / LlamaIndex / Unstructured; ingestion stays small and explicit.

## Local setup

Use Python 3.12.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create `.env` from `.env.example` and provide:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `DEEPSEEK_API_KEY`

Start the API:

```bash
uvicorn app.main:app --reload
```

Start Streamlit from the repository root:

```bash
pip install -r ui/requirements.txt
set API_BASE_URL=http://127.0.0.1:8000
# Linux/macOS: export API_BASE_URL=http://127.0.0.1:8000
streamlit run ui/app.py
```

The existing BM25 index is loaded from `data/bm25/index.joblib`. Rebuild it with the existing indexing workflow when the corpus changes.

## Docker

Docker is **supported but not required** for deployment. The repository contains:

- `Dockerfile` for FastAPI
- `Dockerfile.streamlit` for Streamlit
- `docker-compose.yml` for local full-stack testing

```bash
docker compose up --build
```

The Streamlit container uses `API_BASE_URL=http://api:8000`.

## Deployment

### FastAPI on Render

The repository includes `render.yaml`.

1. Create a Render Blueprint from the `deploy-ready` branch.
2. Provide the six secret environment variables requested by the Blueprint.
3. Render builds with `pip install -r requirements.txt`.
4. The API starts with Uvicorn and exposes `/health`.
5. Copy the resulting `https://...onrender.com` URL.

The deployed retrieval path uses Qdrant Cloud Inference instead of loading a local embedding model. Production retrieval defaults to hybrid RRF. The Cross-Encoder remains available for local/evaluation workflows but is not loaded by default in production, keeping the API compatible with Render's 512 MB free instance.

### Streamlit Community Cloud

Deploy:

```text
Repository: sanjaysiddhudasari/support-knowledge-copilot
Branch: deploy-ready
Main file: ui/app.py
Python: 3.12
```

Streamlit Cloud uses `ui/requirements.txt`. In the app's Secrets settings, add:

```toml
API_BASE_URL = "https://your-render-service.onrender.com"
```

Do not commit real secrets.

## Data persistence note

Qdrant vectors are stored in Qdrant Cloud, while BM25 is bundled with the backend image/repository.

The current admin upload endpoint writes uploaded documents (MD, TXT, PDF, DOCX, HTML) and the regenerated BM25 index to the backend filesystem. On Render, the default filesystem is ephemeral. Therefore uploaded documents are not durable across restarts/redeploys unless a paid persistent disk or an external document/object-storage workflow is added. The committed 120-chunk corpus remains available because it is part of the repository and Qdrant Cloud.

## Production flow

The deployed API does not load the local SentenceTransformer/PyTorch embedding model. Query and document embedding for Qdrant Cloud are handled through Qdrant Cloud Inference using the same `all-MiniLM-L6-v2` model used by the existing 384-dimensional collection.

```text
Streamlit Community Cloud
          |
          | HTTPS + Supabase access token
          v
      Render FastAPI
          |
          +----> Supabase Auth/Postgres
          |
          +----> Qdrant Cloud
          |         |
          |         +---- Cloud Inference
          |              all-MiniLM-L6-v2
          |
          +----> Local BM25 index
          |
          +----> DeepSeek
          |
          v
   Hybrid RRF retrieval
          |
          v
 Answer + verified citations + confidence
```

### Key production design decisions

- **Qdrant Cloud is the managed vector database**; the deployed API does not maintain a local Qdrant database.
- **Embedding inference is offloaded to Qdrant Cloud** so the Render service does not need to load PyTorch/SentenceTransformer for production queries.
- **Hybrid RRF is the production retrieval strategy.**
- **Cross-Encoder reranking remains available for local/evaluation experiments** but is disabled by default in production.
- **BM25 remains local and bundled** because the current corpus is small.
- **Supabase access control is applied after retrieval** so users only receive chunks permitted by their access level.
- **Citation verification is performed against retrieved evidence before confidence is calculated.**

