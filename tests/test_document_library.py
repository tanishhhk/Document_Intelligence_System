import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.models.document import Document
from app.models.user import User

START = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture()
def library(db_session_factory, auth_headers):
    """Seven documents for the current user and one for someone else."""
    user_id, headers = auth_headers
    rows = [
        ("Annual Report 2025.pdf", "completed"),
        ("annual-budget.pdf", "completed"),
        ("Employee Handbook.pdf", "completed"),
        ("scan_of_receipt.pdf", "failed"),
        ("100%_complete.pdf", "completed"),
        ("draft.pdf", "queued"),
        ("contract.pdf", "processing"),
    ]
    ids = []
    with db_session_factory() as db:
        db.add(User(id="other-user", email="other@example.com", hashed_password="x"))
        db.flush()
        for minutes, (filename, status) in enumerate(rows):
            document_id = str(uuid.uuid4())
            ids.append(document_id)
            db.add(
                Document(
                    id=document_id,
                    user_id=user_id,
                    filename=filename,
                    file_path="unused.pdf",
                    file_size=100,
                    status=status,
                    upload_date=START + timedelta(minutes=minutes),
                )
            )
        db.add(
            Document(
                id=str(uuid.uuid4()),
                user_id="other-user",
                filename="Annual Report of another user.pdf",
                file_path="unused.pdf",
                file_size=100,
                status="completed",
                upload_date=START,
            )
        )
        db.commit()
    return headers, ids, [filename for filename, _status in rows]


def _get(headers, **params):
    response = TestClient(app).get("/documents", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_documents_are_paged_newest_first(library):
    headers, _ids, names = library
    first = _get(headers, limit=3)
    second = _get(headers, limit=3, offset=3)
    last = _get(headers, limit=3, offset=6)

    assert first["total"] == 7
    assert [d["filename"] for d in first["items"]] == names[::-1][:3]
    assert [d["filename"] for d in second["items"]] == names[::-1][3:6]
    assert [d["filename"] for d in last["items"]] == names[::-1][6:]
    assert (first["limit"], first["offset"]) == (3, 0)


def test_documents_can_be_listed_oldest_first(library):
    headers, _ids, names = library
    assert [d["filename"] for d in _get(headers, order="oldest")["items"]] == names


def test_a_page_past_the_end_is_empty(library):
    headers, _ids, _names = library
    page = _get(headers, offset=50)
    assert page["items"] == []
    assert page["total"] == 7


def test_documents_can_be_filtered_by_status(library):
    headers, _ids, _names = library
    failed = _get(headers, status="failed")
    assert [d["filename"] for d in failed["items"]] == ["scan_of_receipt.pdf"]
    assert failed["total"] == 1


def test_search_matches_part_of_the_filename_ignoring_case(library):
    headers, _ids, _names = library
    found = _get(headers, q="ANNUAL")
    assert sorted(d["filename"] for d in found["items"]) == ["Annual Report 2025.pdf", "annual-budget.pdf"]
    combined = _get(headers, q="annual", status="completed", limit=1)
    assert combined["total"] == 2
    assert len(combined["items"]) == 1


@pytest.mark.parametrize(
    "term, expected",
    [
        ("%", ["100%_complete.pdf"]),
        ("_", ["100%_complete.pdf", "scan_of_receipt.pdf"]),
        ("\\", []),
        ("' OR '1'='1", []),
        ("%' OR 1=1 --", []),
    ],
    ids=["percent", "underscore", "backslash", "quote-injection", "comment-injection"],
)
def test_search_terms_are_matched_literally(library, term, expected):
    headers, _ids, _names = library
    assert sorted(d["filename"] for d in _get(headers, q=term)["items"]) == expected


def test_other_users_documents_never_appear(library):
    headers, _ids, _names = library
    found = _get(headers, q="another user")
    assert found["items"] == []
    assert found["total"] == 0
    assert _get(headers)["total"] == 7


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"status": "deleted"},
        {"order": "random"},
        {"q": ""},
        {"q": "x" * 201},
    ],
)
def test_invalid_parameters_are_rejected(library, params):
    headers, _ids, _names = library
    response = TestClient(app).get("/documents", headers=headers, params=params)
    assert response.status_code == 422


def test_anonymous_requests_are_rejected():
    assert TestClient(app).get("/documents").status_code == 401


def test_paging_happens_in_the_database(library, db_session_factory):
    headers, _ids, _names = library
    engine = db_session_factory.kw["bind"]
    statements = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        _get(headers, limit=2)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    selects = [s for s in statements if "FROM documents" in s and "count(" not in s.lower()]
    assert any("LIMIT" in s.upper() for s in selects)


def test_the_original_list_endpoint_still_returns_every_document(library):
    headers, _ids, _names = library
    response = TestClient(app).get("/documents/list", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 7
