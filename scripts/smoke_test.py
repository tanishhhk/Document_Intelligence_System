"""Exercise a running deployment end to end.

    BASE_URL=http://localhost:8000 python scripts/smoke_test.py

Registers a throwaway user, uploads a generated PDF, waits for the worker to
process it with the real embedding model, checks paging, retrieval and
cross-user isolation, and deletes the document. When the deployment has no
valid Gemini key, asking a question must fail with the misconfiguration
error rather than a fake success. Exits non-zero on the first failed check.
"""
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.eval.rag_dataset import build_pdf  # noqa: E402

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
EXPECT_ANSWERS = os.environ.get("EXPECT_ANSWERS") == "1"


def check(condition, message):
    if not condition:
        sys.exit(f"FAILED: {message}")
    print(f"ok - {message}")


def wait_until_ready(client):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if client.get("/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    sys.exit("FAILED: service did not become ready")


def account(client):
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    password = "Smoke-test-password-1"
    check(client.post("/auth/register", json={"email": email, "password": password}).status_code == 201,
          "register")
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def main():
    client = httpx.Client(base_url=BASE_URL, timeout=60)
    wait_until_ready(client)
    check("x-request-id" in client.get("/health").headers, "responses carry a request ID")

    owner, stranger = account(client), account(client)
    upload = client.post(
        "/documents/upload",
        headers={**owner, "Idempotency-Key": f"smoke-{uuid.uuid4().hex}"},
        files={"file": ("quarterly_report.pdf", build_pdf("quarterly_report"), "application/pdf")},
    )
    check(upload.status_code == 201 and upload.json()["status"] == "queued", "upload is queued")
    document_id = upload.json()["id"]

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        document = client.get(f"/documents/{document_id}", headers=owner).json()
        if document["status"] in ("completed", "failed"):
            break
        time.sleep(1)
    check(document["status"] == "completed", f"worker processed the document ({document.get('error_message')})")
    check(document["page_count"] == 4 and document["chunk_count"] > 0, "page and chunk counts are stored")

    page = client.get("/documents", headers=owner, params={"q": "quarterly", "status": "completed"}).json()
    check(page["total"] == 1 and page["items"][0]["id"] == document_id, "library search finds the document")
    check(client.get(f"/documents/{document_id}", headers=stranger).status_code == 404,
          "another user cannot see the document")

    ask = client.post(
        "/chat/ask",
        headers=owner,
        json={"question": "Where will the new data centre be opened?", "document_id": document_id},
    )
    if EXPECT_ANSWERS:
        body = ask.json()
        check(ask.status_code == 200 and body["answer_status"] == "answered", "question is answered")
        check(any(s["cited"] and s["page_start"] == 4 for s in body["sources"]), "answer cites page 4")
    else:
        check(ask.status_code == 500 and "not configured" in ask.json()["detail"],
              "an invalid Gemini key is reported as misconfiguration")

    check(client.delete(f"/documents/{document_id}", headers=owner).status_code == 200, "delete")
    check(client.get(f"/documents/{document_id}", headers=owner).status_code == 404, "deleted document is gone")


if __name__ == "__main__":
    main()
