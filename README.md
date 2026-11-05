# Document Intelligence System

A FastAPI service for uploading PDF documents, searching their text, and answering questions with retrieval-augmented generation (RAG).

## Features

- PDF text extraction with file, page, and character limits.
- Text chunking and local embeddings using `all-MiniLM-L6-v2`.
- Similarity-based retrieval of relevant chunks.
- Answers generated with the configured Google Gemini model.
- JWT authentication and per-user document access.
- Upload idempotency keys, logout token revocation, and API request limits.

## Request flow

1. A user uploads a PDF. The service stores it and queues the document.
2. A background worker extracts selectable text and splits it into chunks.
3. The embedding model converts chunks to vectors, which are stored with the document.
4. A question is embedded and compared with the document chunks.
5. The most relevant chunks are sent to Gemini as context.
6. The response includes source chunk references and similarity scores.

The current retrieval implementation compares stored vectors in Python. It does not use a dedicated vector database. Scanned PDFs need OCR, which is not included.

## Stack

| Area | Technology |
|---|---|
| API | FastAPI and Uvicorn |
| Database | SQLAlchemy with SQLite or PostgreSQL |
| Authentication | JWT, bcrypt |
| PDF processing | pypdf |
| Embeddings | sentence-transformers, all-MiniLM-L6-v2 |
| Answer generation | Google GenAI SDK |

## Setup

Python 3.11 is recommended.

```bash
git clone https://github.com/tanishhhk/Document_Intelligence_System.git
cd Document_Intelligence_System

python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
```

On Linux, `pip` installs the CUDA build of PyTorch by default. The service only needs the CPU build, which is much smaller. Install it first with `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

Edit `.env` before starting the service:

- Set `SECRET_KEY` to a randomly generated value of at least 32 characters. You can generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- Set `GEMINI_API_KEY` to a key from Google AI Studio.
- Set `CORS_ORIGINS` to a JSON array containing the exact origins of the frontend. The example includes common local development ports.
- Set `DATABASE_URL` to your database connection string. SQLite is the default example.

The default answer model is `gemini-3.8-flash`. Change it with `GEMINI_MODEL` if needed.

Run the API:

```bash
uvicorn app.main:app --reload
```

The interactive API documentation is available at `http://localhost:8000/docs`.

The first operation that needs embeddings downloads the MiniLM model weights.

The schema is managed with Alembic. By default the API upgrades the database to the latest revision when it starts. Databases created by earlier versions of the project, before migrations existed, are upgraded in place and keep their rows.

When more than one process shares a database, set `AUTO_MIGRATE=false` and run the upgrade once before starting the processes:

```bash
alembic upgrade head
```

Create a new revision after changing a model with `alembic revision --autogenerate -m "describe the change"`, then review the generated file. `tests/test_migrations.py` fails if the models and the migrations disagree.

### Document processing

Each API process runs one background worker thread that processes queued documents. Processing state lives in the database, so documents queued or interrupted by a restart are picked up again when a worker starts. Several workers can run against one database; each document is claimed by one of them under a 15-minute lease.

To run processing separately from the API, set `INGESTION_WORKER_ENABLED=false` on the API processes and start one or more workers:

```bash
python -m app.worker
```

The worker also deletes stored PDFs that have no matching document and are more than an hour old, such as files left behind by a crash.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | SQLite file |
| `SECRET_KEY` | JWT signing key | Required |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `GEMINI_API_KEY` | Gemini API key | Required |
| `GEMINI_MODEL` | Answer generation model | `gemini-3.8-flash` |
| `CORS_ORIGINS` | Explicit browser origins allowed by CORS | Local development origins |
| `AUTO_MIGRATE` | Upgrade the schema on startup | `true` |
| `INGESTION_WORKER_ENABLED` | Run the document processing worker inside the API process | `true` |
| `UPLOAD_DIR` | Where uploaded PDFs are stored | `./uploads` |
| `MAX_FILE_SIZE` | Maximum PDF size in bytes | `10485760` |
| `MAX_PDF_PAGES` | Maximum PDF pages processed | `500` |
| `MAX_PDF_CHARS` | Maximum extracted characters | `500000` |
| `AUTH_REQUESTS_PER_MINUTE` | Request limit for login and registration | `30` |
| `UPLOAD_REQUESTS_PER_MINUTE` | Request limit for upload | `8` |
| `CHAT_REQUESTS_PER_MINUTE` | Request limit for questions | `20` |
| `DEFAULT_REQUESTS_PER_MINUTE` | Limit for other API routes | `120` |
| `MAX_RATE_LIMIT_KEYS` | Maximum tracked peer and route buckets | `10000` |

## API

Registration and login accept JSON. Protected routes require an `Authorization: Bearer <access_token>` header.

### Authentication

**`POST /auth/register`**

```json
{
  "email": "you@example.com",
  "password": "A-strong-password-123"
}
```

Registration requires at least 12 characters. Passwords longer than bcrypt's 72-byte limit are rejected.

**`POST /auth/login`**

Send the same email and password fields. A successful response contains `access_token` and `token_type`.

**`POST /auth/logout`**

Requires the bearer token. The current access token is added to the revocation table.

### Documents

**`POST /documents/upload`**

Multipart form upload with a `file` field and an `Idempotency-Key` header. The key must contain 16 to 128 letters, numbers, dots, underscores, or hyphens. Use a new key for each new upload operation.

The response is `201` with the new document in the `queued` state. Processing happens in the background; poll `GET /documents/{document_id}` until the status is `completed` or `failed`. Asking a question about a document that is not completed returns `409`.

| Retry with the same key | Result |
|---|---|
| Same file, earlier upload completed | `201` with the original document; nothing is processed again |
| Different file | `409`; a key belongs to one file |
| Earlier upload still processing | `409` with `Retry-After` |
| Earlier upload failed | Processed again |
| Earlier upload stopped without finishing, for example on a server restart | Processed again once its 15-minute processing lease expires |
| The document created with the key was deleted | `409`; use a new key |

Files are compared by SHA-256. Keys expire after 24 hours.

Request bodies are limited before they are read: uploads to `MAX_FILE_SIZE` plus 64 KiB of multipart framing, and other requests to 1 MiB.

**`GET /documents/list`**

Lists documents owned by the authenticated user.

**`GET /documents/{document_id}`**

Returns one document if it belongs to the authenticated user, including its processing state:

| `status` | Meaning |
|---|---|
| `queued` | Stored and waiting for the worker |
| `processing` | Being extracted and embedded |
| `completed` | Ready for questions; `chunk_count` and `processed_at` are set |
| `failed` | Not searchable; `error_message` says why |

A file that cannot be processed as uploaded (no selectable text, encrypted, corrupt, over the page or text limits) fails at once. Other errors are retried up to three times before the document is marked failed.

**`POST /documents/{document_id}/retry`**

Queues a failed document for processing again. Returns `409` if the document is not in the `failed` state or its stored file is gone.

**`DELETE /documents/{document_id}`**

Deletes the user's document, chunks, and stored PDF.

### Questions

**`POST /chat/ask`**

```json
{
  "question": "What does the report say about revenue?",
  "document_id": "document-id-from-upload",
  "top_k": 3
}
```

The question is limited to 4,000 characters and `top_k` must be between 1 and 10. The response includes the answer, selected source chunks, similarity scores, and model metadata.

## Tests

Run the test suite from the repository root:

```bash
pytest -q
```

Set `TEST_DATABASE_URL` to run the API tests against a disposable PostgreSQL database, and `TEST_POSTGRES_URL` to include PostgreSQL in the migration tests. CI runs both.

The tests use a local SQLite database by default and mock the embedding and answer-generation calls where appropriate. They do not verify live Gemini credentials, billing, quotas, or network availability.

## Limitations

- The rate limiter stores state in each process. Each worker and instance counts separately. Use a shared store such as Redis or a trusted gateway for multi-worker deployments.
- Behind a reverse proxy, start Uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy address>` so the limiter sees client addresses instead of the proxy's.
- Rate limiting and upload caps do not replace network-level DDoS protection.
- Scanned PDFs need an OCR implementation.
- Retrieval scans stored vectors in Python, which may become slow as the number of chunks grows.
- This repository is a prototype and has not undergone a formal security audit.

See [SECURITY.md](SECURITY.md) for details about covered attack surfaces and remaining limits.
