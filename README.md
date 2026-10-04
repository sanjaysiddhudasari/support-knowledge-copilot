# Support Knowledge Copilot

A RAG-based support knowledge assistant with multi-format document ingestion (Markdown, TXT, PDF, DOCX, HTML), hybrid retrieval, access control, document versioning, freshness-aware retrieval, and verified citations.

## Architecture

- **Frontend:** Streamlit (chat UI with persistent per-message confidence/citations, sidebar knowledge base, format-aware source cards)
- **API:** FastAPI
- **Vector store:** Qdrant Cloud
- **Deployed embeddings:** Qdrant Cloud Inference using `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Lexical retrieval:** BM25 index stored in `data/bm25/index.joblib`
- **Hybrid retrieval:** Reciprocal Rank Fusion (RRF), used as the production default
- **Reranking:** Cross-Encoder is supported for local/evaluation workflows but disabled by default in production to avoid its additional memory footprint
- **Generation + citation verification:** DeepSeek
- **Authentication + user profiles:** Supabase Auth (login **and** sign up) + Supabase Postgres `profiles`
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

## Citations and document type

Every citation carries the format of the document it came from, so the UI never
has to re-detect anything:

```json
{
  "chunk_id": "manual.pdf_chunk_2",
  "claim": "...",
  "supported": true,
  "explanation": "...",
  "source": "manual.pdf",
  "file_type": "pdf",
  "page": 2
}
```

`file_type` is the normalized value produced by the loader (`markdown`, `text`,
`pdf`, `docx`, `html`). It is **not** `document_type`, which is semantic
metadata such as `guide`. `page` is present for PDFs only. The trace is:

```text
loader → LoadedDocument.file_type → Chunk.file_type → Qdrant payload
      → retrieval result → Citation → API response → Streamlit UI
```

Display mapping (single map in `ui/chat_state.py`):

| `file_type` | Display |
|---|---|
| `markdown` | 📚 Markdown |
| `text` | 📝 Text |
| `pdf` | 📄 PDF |
| `docx` | 📘 DOCX |
| `html` | 🌐 HTML |

Anything missing or unknown falls back to `📎 Document`. `POST /api/documents`
returns the normalized `file_type` of the uploaded file, and old chunks without
`file_type` remain fully compatible.

## Authentication and access levels

- `POST /api/auth/login` — existing email/password login via Supabase.
- `POST /api/auth/signup` — creates the Supabase user, then provisions a
  `profiles` row (`id`, `email`, `access_level`) with the service-role client,
  which is used by the API only. The write is an idempotent upsert, so a
  database trigger that already creates profiles is not duplicated.
- New accounts are always created with `access_level = public`. No code path
  grants `admin` at signup.
- Supabase may require email confirmation, so the endpoint answers with either
  `status: "success"` (session included) or `status: "confirmation_required"`;
  the UI handles both.
- The service-role key never reaches Streamlit, which only holds the user's
  access token.

## Frontend (Streamlit)

One app, `ui/app.py`:

- **Auth screen** — `Login` / `Sign Up` tabs. Sign up collects email, password
  and confirmation; the email shape, the 8-character minimum and the match are
  validated by the backend (and cheaply pre-checked in the UI).
- **Sidebar** — `+ New Chat`, knowledge-base upload (`MD · TXT · PDF · DOCX ·
  HTML`) showing the indexed type after upload, the signed-in user with their
  access level, and `Logout`.
- **Persistent conversation** — every assistant turn stores its own answer,
  confidence, answerability and citations in session state. History is rendered
  from that stored metadata, so an older answer keeps *its* confidence and
  sources after later questions. Nothing is recomputed or borrowed from the
  latest query. `+ New Chat` clears the conversation without signing out.
- **Sources** — format-aware expandable cards, e.g.
  `manual.pdf · PDF · Page 7 · Verified`.
- **Loading / errors** — a status line for "Searching documentation…" and
  "Verifying citations…"; a failed query keeps the question and every earlier
  answer on screen.

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

The API base URL is read from Streamlit secrets when a `secrets.toml` exists
and from the `API_BASE_URL` environment variable otherwise, so a missing
secrets file no longer prevents local runs.

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

