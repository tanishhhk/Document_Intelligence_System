"""Property-based tests: invariants that must hold for any input Hypothesis can generate."""
import asyncio
import re
import string
from types import SimpleNamespace

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, String, Table, create_engine, insert, select

from app.api.documents import _display_filename, _escape_like
from app.config import Settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import _ID_CHARACTERS, _request_id
from app.services import llm
from app.services.auth import decode_access_token, token_user_id
from app.services.retrieval import RetrievedChunk
from app.utils.pdf_processor import extract_pages
from app.utils.text_processor import chunk_pages

words = st.one_of(
    st.text(alphabet=string.ascii_letters + string.digits + "%$-'", min_size=1, max_size=12),
    # Occasionally very long unbroken tokens, such as URLs or encoded data.
    st.text(alphabet=string.ascii_letters + string.digits, min_size=200, max_size=3000),
)
sentences = st.builds(
    lambda ws, end: " ".join(ws).capitalize() + end,
    st.lists(words, min_size=1, max_size=40),
    st.sampled_from([".", "!", "?", ""]),
)
lines = st.one_of(
    sentences,
    st.builds(lambda ws: " | ".join(ws), st.lists(words, min_size=2, max_size=5)),  # table rows
    st.builds(lambda w: f"- {w}", sentences),  # list items
    st.builds(lambda n, w: f"{n}. {w.title()}", st.integers(1, 20), words),  # numbered headings
    st.just(""),
)
pages = st.lists(st.lists(lines, max_size=30).map("\n".join), min_size=1, max_size=6)



# Chunking


@example(
    # Found by the nightly profile: a heading followed by a sentence longer
    # than the chunk size was dropped.
    ["0 0 0 00 000000 0000000 0000000 000000000000 000000000000\n" + " ".join(["0" * 9] * 24) + "."],
    200,
)
@given(pages, st.integers(200, 1500))
def test_chunking_never_loses_or_invents_text(page_texts, chunk_size):
    numbered = list(enumerate(page_texts, start=1))
    chunks = chunk_pages(numbered, chunk_size=chunk_size, overlap=chunk_size // 5, max_chunk_size=chunk_size * 3 // 2)

    # Whitespace is not content; compare the rest. Words longer than a chunk
    # are cut into pieces, so check substrings rather than whole tokens.
    source = "".join(" ".join(page_texts).split())
    joined_chunks = "".join("".join(c.text.split()) for c in chunks)
    for word in " ".join(page_texts).split():
        assert word in joined_chunks, f"lost: {word[:40]}"
    for chunk in chunks:
        for token in chunk.text.split():
            assert token in source, f"invented: {token[:40]}"


@given(pages, st.integers(200, 1500))
def test_chunks_are_bounded_non_empty_and_have_valid_pages(page_texts, chunk_size):
    numbered = list(enumerate(page_texts, start=1))
    max_size = chunk_size * 3 // 2
    chunks = chunk_pages(numbered, chunk_size=chunk_size, overlap=chunk_size // 5, max_chunk_size=max_size)
    for chunk in chunks:
        assert chunk.text.strip()
        # A heading (at most 80 characters) can precede a segment of max_size.
        assert len(chunk.text) <= max_size + 81
        assert 1 <= chunk.page_start <= chunk.page_end <= len(page_texts)


@given(pages)
def test_chunking_is_deterministic(page_texts):
    numbered = list(enumerate(page_texts, start=1))
    assert chunk_pages(numbered) == chunk_pages(numbered)


# Prompt construction and citations


source_texts = st.text(max_size=300)


@given(st.lists(source_texts, min_size=1, max_size=5), st.text(max_size=200))
def test_document_text_can_never_open_or_close_source_elements(texts, question):
    sources = [RetrievedChunk(f"S{i + 1}", i, text, 1, 1, 0.5) for i, text in enumerate(texts)]
    message = llm.build_user_message(question, sources)
    body = message.rsplit("\n\nQuestion: ", 1)[0]
    assert len(re.findall(r"<\s*source", body, re.IGNORECASE)) == len(sources)
    assert len(re.findall(r"<\s*/\s*source", body, re.IGNORECASE)) == len(sources)


@given(st.text(max_size=300), st.integers(1, 10))
def test_cleaned_answers_cite_only_retrieved_sources(answer, count):
    sources = [RetrievedChunk(f"S{i + 1}", i, "text", 1, 1, 0.5) for i in range(count)]
    cleaned, cited = llm.cited_source_ids(answer, sources)
    known = {s.source_id for s in sources}
    assert {f"S{n}" for n in re.findall(r"\[S(\d+)\]", cleaned)} <= known
    assert set(cited) <= known
    assert len(cited) == len(set(cited))
    assert llm.cited_source_ids(cleaned, sources) == (cleaned, cited)  # Cleaning is idempotent.


@given(st.lists(source_texts, min_size=1, max_size=10))
def test_the_extractive_fallback_lists_every_source_briefly(texts):
    sources = [RetrievedChunk(f"S{i + 1}", i, text, None, None, 0.5) for i, text in enumerate(texts)]
    answer, cited = llm.extractive_answer(sources)
    assert cited == [s.source_id for s in sources]
    assert answer.startswith("An AI answer is not available")
    for source in sources:
        assert f"[{source.source_id}]" in answer
    assert len(answer) <= 200 + len(sources) * 420


# Input handling


@given(st.text(max_size=2000))
def test_display_filenames_are_safe(raw):
    name = _display_filename(raw)
    assert len(name) <= 255
    assert "/" not in name and "\\" not in name
    assert all(ch.isprintable() for ch in name)


@given(st.text(max_size=5).map(lambda s: s + ".pdf"), st.integers(0, 3000))
def test_long_pdf_filenames_keep_their_extension(stem, padding):
    assert _display_filename("x" * padding + stem).lower().endswith(".pdf") or "/" in stem or "\\" in stem


_like_engine = create_engine("sqlite://")
_like_table = Table("names", MetaData(), Column("name", String))
_like_table.metadata.create_all(_like_engine)


@given(st.text(alphabet=string.ascii_letters + "%_\\ -.'", max_size=8), st.text(alphabet=string.ascii_letters + "%_\\ -.'", max_size=20))
def test_filename_search_matches_exactly_when_the_term_is_contained(term, name):
    assume(term)
    with _like_engine.begin() as connection:
        connection.execute(_like_table.delete())
        connection.execute(insert(_like_table).values(name=name))
        pattern = f"%{_escape_like(term)}%"
        found = connection.execute(
            select(_like_table.c.name).where(_like_table.c.name.ilike(pattern, escape="\\"))
        ).first()
    assert (found is not None) == (term.lower() in name.lower())


@given(st.binary(max_size=200))
def test_request_ids_are_always_safe(supplied):
    request_id = _request_id({"headers": [(b"x-request-id", supplied)]})
    assert 1 <= len(request_id) <= 64
    assert set(request_id) <= _ID_CHARACTERS


@given(st.text(max_size=500))
def test_token_decoding_never_raises(token):
    assert decode_access_token(token) is None
    assert token_user_id(token) is None


@given(st.lists(st.text(max_size=60), max_size=5), st.text(max_size=60))
def test_provider_and_cors_settings_never_fail_with_unexpected_errors(origins, providers):
    try:
        Settings(_env_file=None, database_url="sqlite://", secret_key="s" * 64, cors_origins=origins, llm_providers=providers)
    except ValidationError:
        pass


@given(st.binary(max_size=400))
def test_the_pdf_reader_only_ever_raises_value_errors(data):
    try:
        pages_found = extract_pages(b"%PDF-1.7\n" + data, max_pages=5, max_chars=10_000)
    except ValueError:
        return
    assert all(isinstance(text, str) for _number, text in pages_found)


# Rate limiting


@given(
    st.lists(st.tuples(st.sampled_from(["10.0.0.1", "10.0.0.2", "10.0.0.3"]), st.sampled_from(["/a", "/auth/login"])),
             max_size=60),
    st.integers(1, 5),
    st.integers(1, 4),
)
def test_no_caller_exceeds_its_limit_and_tracking_stays_bounded(calls, limit, max_keys):
    async def ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limits = SimpleNamespace(auth_requests_per_minute=limit, upload_requests_per_minute=limit,
                             chat_requests_per_minute=limit, default_requests_per_minute=limit,
                             max_rate_limit_keys=max_keys + 100)
    limiter = RateLimitMiddleware(ok, limits)
    limiter.max_tracked_keys = max_keys
    allowed = {}

    async def run():
        for ip, path in calls:
            statuses = []

            async def send(message, statuses=statuses):
                if message["type"] == "http.response.start":
                    statuses.append(message["status"])

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            await limiter({"type": "http", "method": "POST", "path": path, "headers": [], "client": (ip, 1)}, receive, send)
            bucket = "auth" if path == "/auth/login" else "general"
            if statuses[0] == 200:
                allowed[(ip, bucket)] = allowed.get((ip, bucket), 0) + 1
            assert len(limiter.requests) <= max_keys

    asyncio.run(run())
    if max_keys >= 6:  # With room for every key nothing is evicted, so counts are exact.
        assert all(count <= limit for count in allowed.values())


@pytest.mark.parametrize("limit", [1, 3])
def test_the_limit_is_exact_when_nothing_is_evicted(limit):
    test_no_caller_exceeds_its_limit_and_tracking_stays_bounded.hypothesis.inner_test(
        [("10.0.0.1", "/a")] * (limit + 5), limit, 10
    )
