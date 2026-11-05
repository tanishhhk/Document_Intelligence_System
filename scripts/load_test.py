"""Simulate several people using the API at once.

    BASE_URL=http://localhost:8000 USERS=10 python scripts/load_test.py

Each simulated user registers, uploads the sample handbook, waits for it to be
read and asks three questions, all at the same time as the others. Prints
response times and any failures. Every user counts against the API's limits
like a real one, and questions use the configured model quota.
"""
import asyncio
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.eval.rag_dataset import build_pdf  # noqa: E402

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
USERS = int(os.environ.get("USERS", "10"))
QUESTIONS = [
    "How many days of annual leave do full-time employees get?",
    "When do expense claims have to be submitted?",
    "How many days a week can I work from home?",
]
PDF = build_pdf("handbook")


async def timed(timings, name, call):
    started = time.perf_counter()
    response = await call
    timings.setdefault(name, []).append(time.perf_counter() - started)
    return response


async def one_user(client, timings, failures):
    email = f"load-{uuid.uuid4().hex[:10]}@example.com"
    credentials = {"email": email, "password": "load test password 1"}
    try:
        await timed(timings, "register", client.post("/auth/register", json=credentials))
        login = await timed(timings, "login", client.post("/auth/login", json=credentials))
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        upload = await timed(timings, "upload", client.post(
            "/documents/upload",
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            files={"file": ("handbook.pdf", PDF, "application/pdf")},
        ))
        document_id = upload.json()["id"]
        started = time.perf_counter()
        while True:
            status = (await client.get(f"/documents/{document_id}", headers=headers)).json()["status"]
            if status in ("completed", "failed"):
                break
            await asyncio.sleep(1)
        timings.setdefault("processing", []).append(time.perf_counter() - started)
        if status != "completed":
            failures.append(f"{email}: document {status}")
            return
        for question in QUESTIONS:
            answer = await timed(timings, "question", client.post(
                "/chat/ask", headers=headers, json={"question": question, "document_id": document_id}
            ))
            if answer.status_code != 200:
                failures.append(f"{email}: question returned {answer.status_code}")
    except Exception as exc:  # Report and keep the other users going.
        failures.append(f"{email}: {type(exc).__name__}: {exc}")


async def main():
    timings, failures = {}, []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180) as client:
        started = time.perf_counter()
        await asyncio.gather(*(one_user(client, timings, failures) for _ in range(USERS)))
        total = time.perf_counter() - started
    print(f"{USERS} users in {total:.1f}s against {BASE_URL}")
    for name, values in timings.items():
        values.sort()
        p95 = values[max(0, int(len(values) * 0.95) - 1)]
        print(f"  {name:<11} n={len(values):<3} median {statistics.median(values):.2f}s  p95 {p95:.2f}s  max {values[-1]:.2f}s")
    print(f"failures: {len(failures)}")
    for failure in failures[:20]:
        print(f"  {failure}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
