# Document Intelligence System

A FastAPI backend for question-answering over PDF documents with retrieval-augmented generation (RAG). Users register and sign in, upload text-based PDFs, and ask questions grounded in retrieved document chunks.

## Architecture

1. Stream an uploaded PDF to disk with a configurable size cap.
2. Extract selectable text with `pypdf`; image-only/scanned PDFs require OCR and are rejected with a clear error for now.
3. Split text into overlapping chunks and create normalized `all-MiniLM-L6-v2` embeddings.
4. Store document metadata, chunks, and JSON-serialized vectors in SQL.
5. Retrieve the highest cosine-similarity chunks for a question and pass those passages to Gemini 3.8 Flash (configurable).
6. Return the answer and source chunk IDs/similarity scores.

Retrieval is exact brute-force cosine over the selected document's chunks. A vector database is not currently used.

## Stack

- Python, FastAPI, Uvicorn
- SQLAlchemy with SQLite by default; PostgreSQL can be configured with `DATABASE_URL`
- JWT bearer authentication and bcrypt password hashing
- Sentence Transformers, NumPy, pypdf
- Google Gemini API

## Setup

Python 3.10+ recommended.

```bash
git clone https://github.com/tanishhhk/Document_Intelligence_System.git
cd Document_Intelligence_System
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, generate a unique secret, and add a Gemini API key:

```bash
# macOS/Linux; on Windows, create a random secret with an equivalent secure tool
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `SECRET_KEY` to the generated value and `GEMINI_API_KEY` to your key. Keep `.env` out of Git. Configure `CORS_ORIGINS` as a JSON array containing the exact origins of your frontend. Defaults allow only local development origins on port 3000.

Start the API from the repository root:

```bash
uvicorn app.main:app --reload
```

API docs: <http://127.0.0.1:8000/docs>

The embedding model is downloaded the first time an embedding is requested, so first-time processing requires network access and additional disk space.

## Endpoints

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET | `/` | No | Service information |
| GET | `/health` | No | Liveness check |
| POST | `/auth/register` | No | Register an account |
| POST | `/auth/login` | No | Obtain a bearer token |
| POST | `/documents/upload` | Bearer token | Upload and index a PDF |
| GET | `/documents/list` | Bearer token | List the current user's documents |
| GET | `/documents/{document_id}` | Bearer token | Read an owned document |
| DELETE | `/documents/{document_id}` | Bearer token | Delete an owned document and its chunks |
| POST | `/chat/ask` | Bearer token | Ask a question about an owned document |

### Login and protected requests

Register and log in through the API docs. Copy the returned `access_token`, then send it in the HTTP header:

```
Authorization: Bearer <access_token>
```

Example question request:

```json
{
  "question": "What is the policy's cancellation period?",
  "document_id": "<id returned by upload>",
  "top_k": 3
}
```

The API limits `top_k` to 1-10 and question text to 4,000 characters. Uploads are streamed and capped by `MAX_FILE_SIZE` (10 MiB by default). Each document operation is scoped to the authenticated owner; another user's document is reported as not found.

## Tests

Install the API test dependencies and run the regression suite:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

The tests verify route prefixes, registration/login, authentication requirements, per-user document isolation, upload ownership, and the `top_k` bound. The upload test stubs the embedding pipeline so it does not download model weights or call external AI services.

## Important limitations

- PDF ingestion and Gemini response generation still happen synchronously within the request, although CPU-bound extraction/embedding work is moved off the async event loop. Large files may take time and tie up request workers.
- Scanned PDFs have no OCR path.
- Embeddings are stored as JSON in SQL and searched in Python; this is fine for a small demo, not a high-scale retrieval system.
- Tables are currently created through SQLAlchemy `create_all`; schema migrations are not configured.
- CORS origins must be set for the actual frontend host before deployment.
- Set a strong, unique `SECRET_KEY`, protect the Gemini key, use HTTPS, and configure database/upload storage appropriately for deployment.
- This repository is a portfolio-grade prototype; do not treat it as a security-audited production service.

## License

No license is currently specified. Add one before reuse.
