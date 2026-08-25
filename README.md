# Support Knowledge Copilot

A support knowledge assistant built around **hybrid RAG, reranking, grounded answer generation, and verified citations**. It answers questions from a synthetic AcmeCloud support corpus and explicitly abstains when the available documentation is insufficient.

## What this project demonstrates

A basic RAG demo retrieves a few chunks and asks an LLM to answer. This project goes further by evaluating and inspecting the retrieval and grounding pipeline separately:

- Dense semantic retrieval with Sentence Transformers + Qdrant
- Sparse lexical retrieval with BM25
- Reciprocal Rank Fusion (RRF) for hybrid retrieval
- Reranking before generation
- Metadata-aware document ingestion
- Grounded answer generation from retrieved evidence only
- Citation parsing and LLM-based citation verification
- Answerability / no-answer handling
- Confidence scoring
- Golden-set retrieval and end-to-end evaluation
- FastAPI backend and Streamlit UI
- Dynamic Markdown document upload and re-indexing
- Docker/Compose deployment configuration

## Architecture

```text
                         ┌─────────────────────┐
                         │      Streamlit      │
                         │    Chat + Upload    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       FastAPI       │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
             Dense Retrieval                  BM25 Retrieval
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                             Hybrid / RRF
                                    │
                                    ▼
                                Reranker
                                    │
                                    ▼
                             Top-k evidence
                                    │
                                    ▼
                              LLM Generator
                                    │
                       ┌────────────┴────────────┐
                       │                         │
                       ▼                         ▼
                Citation Parser           Answerability
                       │                         │
                       ▼                         │
              Citation Verifier                 │
                       │                         │
                       └────────────┬────────────┘
                                    ▼
                               Confidence
                                    │
                                    ▼
                              Final Response
```

## Corpus

The project uses a **synthetic AcmeCloud support corpus** created for reproducible evaluation. It covers areas such as authentication, password policy, MFA, account recovery, user management, access control, projects, file storage/sharing, API usage, billing, notifications, troubleshooting, security, and release notes.

The corpus currently contains **15 documentation files and 106 indexed chunks** for the core evaluation setup.

## Retrieval evaluation

The golden retrieval evaluation contains **70 questions**, including answerable questions, multi-chunk questions, ambiguous questions, outdated-information cases, and explicit no-answer cases.

Current retrieval diagnostics from the core corpus:

| Strategy | Recall@5 | Recall@10 | Recall@20 |
|---|---:|---:|---:|
| Dense | 87.36% | 89.66% | **96.55%** |
| BM25 | 67.82% | 80.46% | 83.91% |
| Hybrid | 82.76% | **94.25%** | 94.25% |
| Hybrid + Rerank | **86.21%** | 93.10% | 94.25% |

The diagnostic stage analysis showed only **3/84 expected chunks** lost from Dense to Hybrid in the measured candidate set, and **0/82** lost from Hybrid to reranking.

## End-to-end evaluation

The current end-to-end evaluation measures answerability, citation validity, citation support, and confidence.

A recent run produced:

| Metric | Result |
|---|---:|
| Answerability accuracy | 85.71% |
| Citation validity | 100% |
| Citation support | 92.77% |
| Total evaluated questions | 70 |

The remaining errors are intentionally retained as useful evaluation cases rather than hidden. They include ambiguous queries, multi-document cases, and citation/answerability edge cases.

## Assistant contract

Input:

```json
{
  "query": "How do I reset my password?"
}
```

Output contains:

- grounded answer
- answerability flag
- verified citations
- confidence score

When the corpus does not contain enough evidence, the assistant abstains instead of inventing an answer.

## Running locally

### Install dependencies

```bash
pip install -r requirements.txt
```

### Build the indexes

```bash
python -m app.ingestion.reindex
```

### Start the API

```bash
uvicorn app.main:app --reload
```

### Start the UI

```bash
streamlit run ui/app.py
```

The API is available at `http://localhost:8000` and the Streamlit UI at `http://localhost:8501`.

## Docker

Docker files are included for Linux-based container deployment:

```bash
docker compose build
docker compose up
```

The application persists the `data/` directory so the BM25 and Qdrant indexes can be regenerated and retained across container restarts.

## Project structure

```text
app/
├── api/
├── evaluation/
├── generation/
├── ingestion/
├── models/
├── retrieval/
├── services/
└── main.py

ui/
└── app.py

data/
├── raw/
└── golden/

Dockerfile
aDockerfile.streamlit
docker-compose.yml
requirements.txt
```

## Design decisions

### Why Dense + BM25?

Semantic retrieval is good at paraphrases and conceptual similarity. BM25 is strong for exact strings such as API names, configuration keys, and error codes. Keeping both indexes over the same chunk IDs makes their outputs easy to fuse and inspect.

### Why rerank?

Hybrid retrieval produces a broader candidate set. Reranking then focuses the small set passed to generation on the most query-relevant evidence.

### Why verify citations?

A generated citation is not trustworthy merely because the model produced it. The verifier checks whether the cited retrieved chunk actually supports the claim attached to it.

## Limitations and next improvements

- Conversational query rewriting is not implemented yet; ambiguous questions are evaluated as standalone queries.
- Citation claim extraction can still be improved for complex list/code formatting.
- The current corpus is synthetic and intended for engineering evaluation rather than production knowledge.
- A production deployment should add authentication/authorization, persistent hosted storage, rate limiting, and operational observability.
