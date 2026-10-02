# Support Knowledge Copilot

A RAG-based support knowledge assistant with hybrid retrieval, access control, document versioning, freshness-aware retrieval, and verified citations.

## Architecture

- **Frontend:** Streamlit
- **API:** FastAPI
- **Dense retrieval:** Sentence Transformers + Qdrant Cloud
- **Lexical retrieval:** BM25 index stored in `data/bm25/index.joblib`
- **Hybrid retrieval:** Reciprocal Rank Fusion (RRF)
- **Reranking:** Cross-Encoder
- **Generation + citation verification:** DeepSeek
- **Authentication + user profiles:** Supabase Auth + Supabase Postgres
- **Access levels:** public, internal, admin

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

The Blueprint uses the 2 GB `1c-2g` web-service plan because the current retrieval pipeline loads both an embedding model and a Cross-Encoder reranker.

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

The current admin upload endpoint writes uploaded Markdown and the regenerated BM25 index to the backend filesystem. On Render, the default filesystem is ephemeral. Therefore uploaded documents are not durable across restarts/redeploys unless a paid persistent disk or an external document/object-storage workflow is added. The committed 120-chunk corpus remains available because it is part of the repository and Qdrant Cloud.

## Production flow

```text
Streamlit Cloud
      |
      | HTTPS + Supabase access token
      v
Render FastAPI
      |----> Supabase Auth/Postgres
      |----> Qdrant Cloud
      |----> local BM25 index
      |----> DeepSeek
      v
Answer + verified citations
```
