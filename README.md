# Document Intelligence System

A FastAPI backend for question-answering over PDF documents using retrieval-augmented generation (RAG). Upload a PDF, ask questions about it in natural language, get answers grounded in the document with cited source chunks.

---

## How it works

```
PDF upload
   -> pypdf text extraction
   -> character chunking (1000 chars, 200 overlap)
   -> sentence-transformers embeddings (all-MiniLM-L6-v2, 384-dim)
   -> chunks + embeddings persisted to SQL

Question
   -> embed the question with the same model
   -> cosine similarity against every chunk of the target document
   -> top-k chunks joined into a context block
   -> Gemini 2.5 Flash answers from that context only
   -> answer returned with source chunk indices and similarity scores
```

Retrieval is exact (brute-force cosine over all chunks), not approximate. No vector database — embeddings are stored as JSON in a `TEXT` column and scored in Python.

---

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (default) / PostgreSQL |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2`, runs locally, no API cost |
| LLM | Google Gemini 2.5 Flash |
| Auth | JWT (python-jose) + bcrypt password hashing |
| PDF | pypdf |

---

## Project layout

```
app/
├── main.py                     FastAPI app, CORS, router registration
├── config.py                   Pydantic Settings, loaded from .env
├── database.py                 Engine, SessionLocal, get_db dependency
│
├── api/                        HTTP layer — routing and validation only
│   ├── auth.py                 register, login
│   ├── documents.py            upload, list, get, delete
│   └── chat.py                 ask (retrieval + generation)
│
├── services/                   Business logic, no FastAPI imports
│   ├── auth.py                 hashing, JWT encode/decode
│   ├── embeddings.py           model loaded once at import
│   ├── llm.py                  Gemini call with 429 backoff
│   └── video_generator.py      experimental, not wired up (see Known Issues)
│
├── models/                     SQLAlchemy tables
│   ├── user.py
│   ├── document.py
│   └── document_chunk.py
│
├── schemas/                    Pydantic request/response contracts
│   ├── user.py
│   └── document.py
│
└── utils/
    ├── pdf_processor.py        text extraction
    └── text_processor.py       overlapping chunker
```

---

## Setup

**Requirements:** Python 3.10+

```bash
git clone https://github.com/tanishhhk/Document_Intelligence_System.git
cd Document_Intelligence_System

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install sentence-transformers email-validator numpy
```

> The three extra packages are imported by the code but missing from `requirements.txt`. Without them the app fails at import. See Known Issues.

Create a `.env` in the project root:

```env
DATABASE_URL=sqlite:///./document_intelligence.db
SECRET_KEY=<openssl rand -hex 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=10485760
```

Run:

```bash
uvicorn app.main:app --reload
```

Interactive docs at `http://localhost:8000/docs`.

First upload downloads the MiniLM weights (~90 MB) and will be slow.

---

## API

Paths below are the routes as currently registered. `auth` and `documents` have a duplicated prefix — see Known Issues #1.

### Auth

**`POST /auth/auth/register`**
```json
{ "email": "you@example.com", "password": "hunter2" }
```
→ `201` with `{ id, email, created_at }`

**`POST /auth/auth/login`**
```json
{ "email": "you@example.com", "password": "hunter2" }
```
→ `200` with `{ access_token, token_type }`

### Documents

**`POST /documents/documents/upload`** — `multipart/form-data`, field `file`, PDF only.
Extracts, chunks, embeds, and persists synchronously. Returns the document record.

**`GET /documents/documents/list`** — all documents.

**`GET /documents/documents/{document_id}`** — one document.

**`DELETE /documents/documents/documents/{document_id}`** — removes the file from disk, its chunks, and the record.

### Chat

**`POST /chat/ask`**
```json
{ "question": "What is the refund policy?",
  "document_id": "5f2c...",
  "top_k": 3 }
```

Response:
```json
{
  "answer": "...",
  "document_name": "policy.pdf",
  "sources": [
    { "chunk_index": 12, "similarity_score": 0.81, "preview": "..." }
  ],
  "metadata": { "chunks_searched": 47, "top_k_used": 3, "model": "gemini-2.5-flash" }
}
```

### Misc

`GET /` — service info. `GET /health` — liveness.

---

## Known issues

Documented rather than hidden. Ordered by how much they block you.

1. **Duplicated router prefixes.** `api/auth.py` and `api/documents.py` set `prefix=` on their `APIRouter`, and `main.py` sets it again on `include_router`. FastAPI concatenates, producing `/auth/auth/register` and `/documents/documents/upload`. The delete route is triple-prefixed. Fix by removing `prefix=` from the two `APIRouter(...)` constructors.

2. **Missing dependencies.** `sentence-transformers`, `email-validator`, and `numpy` are imported but unpinned. `langchain`, `langchain-openai`, `openai`, `aiofiles`, `python-docx`, and `passlib` are pinned but unused. `google-generativeai` has no version constraint.

3. **Authentication is not enforced.** JWTs are issued but never verified — `decode_access_token` has no callers, and there is no `get_current_user` dependency. `documents.py` hardcodes `user_id="temp-user-id"`, and `/list` and `/ask` are unauthenticated and unscoped. Do not deploy this publicly as-is.

4. **`services/video_generator.py` does not run.** Missing imports (`time`, `DocumentChunk`), depends on the removed `moviepy.editor` module and the pre-1.x ElevenLabs SDK, and neither package is in requirements. Experimental, imported nowhere.

5. **Postgres is not actually supported.** `database.py` hardcodes `connect_args={"check_same_thread": False}`, which is SQLite-only, despite `psycopg` being installed. Gate it on the URL scheme.

6. **Upload blocks the event loop.** The endpoint is `async def` but calls synchronous, CPU-bound extraction and embedding. A large PDF stalls every concurrent request. Belongs in `BackgroundTasks` — the `status` column already defaults to `"processing"` in anticipation of that.

7. **Scanned PDFs fail silently.** Image-only pages yield empty text, the document is still marked `completed`, zero chunks are stored, and `/chat/ask` later 404s. No OCR fallback.

8. **`MAX_FILE_SIZE` is never checked.** The whole upload is read into memory unbounded.

9. **CORS is fully open.** `allow_origins=["*"]` with `allow_credentials=True`.

10. **No migrations.** `Base.metadata.create_all()` runs at import; schema changes require dropping the database. No Alembic.

11. **`top_k` is unbounded** — a large value stuffs the entire document into the prompt.

---

## Roadmap

- [ ] Fix router prefixes and pin the real dependency set
- [ ] `get_current_user` dependency; scope documents and questions to the owner
- [ ] Move ingestion to `BackgroundTasks`, drive the `status` column properly
- [ ] pgvector + HNSW index to replace in-Python cosine scan
- [ ] Alembic migrations
- [ ] Semantic chunking (`RecursiveCharacterTextSplitter`) instead of fixed character windows
- [ ] Multi-turn chat with conversation history
- [ ] Cross-document retrieval
- [ ] DOCX and TXT ingestion (`python-docx` is already a dependency)
- [ ] OCR fallback for scanned PDFs
- [ ] Tests, Dockerfile, `.env.example`
- [ ] Frontend

---

## License

Not currently licensed. Add one before reuse.
