import sys
import time

import pytest

from app.services import ingestion
from app.utils.isolated import IsolationCrashed, IsolationTimeout, run_isolated
from tests import fakes
from tests.pdf_factory import make_pdf


def test_results_come_back_from_the_child_process():
    assert run_isolated(fakes.pages_of, "hello", timeout=30) == [(1, "hello")]


def test_value_errors_keep_their_message():
    with pytest.raises(ValueError, match="900 pages"):
        run_isolated(fakes.reject, timeout=30)


def test_other_errors_name_their_type_only():
    with pytest.raises(RuntimeError, match="KeyError"):
        run_isolated(fakes.fail_unexpectedly, timeout=30)


def test_a_function_that_never_returns_is_stopped():
    started = time.monotonic()
    with pytest.raises(IsolationTimeout):
        run_isolated(fakes.sleep_forever, timeout=2)
    assert time.monotonic() - started < 15


def test_a_child_that_exits_without_a_result_is_reported():
    with pytest.raises(IsolationCrashed):
        run_isolated(fakes.exit_abruptly, timeout=30)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="memory limits use RLIMIT_DATA on Linux")
def test_memory_use_is_capped_on_linux():
    with pytest.raises(MemoryError):
        run_isolated(fakes.allocate, 2048, timeout=30, memory_limit_bytes=512 * 1024 * 1024)


def test_real_pdfs_are_parsed_in_isolation(monkeypatch):
    monkeypatch.setattr(
        ingestion, "generate_embeddings", lambda texts: [fakes.vector(i) for i in range(len(texts))]
    )
    chunks, _vectors, page_count = ingestion.extract_and_embed_pdf(make_pdf([["Hello world."]]))
    assert [c.text for c in chunks] == ["Hello world."]
    assert page_count == 1


def test_a_pdf_that_hangs_the_parser_is_rejected(monkeypatch):
    monkeypatch.setattr(ingestion, "extract_pages", fakes.sleep_forever)
    monkeypatch.setattr(ingestion.settings, "pdf_parse_timeout_seconds", 2)
    with pytest.raises(ingestion.DocumentRejected, match="took too long"):
        ingestion.extract_and_embed_pdf(b"%PDF-1.7")


def test_a_pdf_that_crashes_the_parser_is_rejected(monkeypatch):
    monkeypatch.setattr(ingestion, "extract_pages", fakes.exit_abruptly)
    with pytest.raises(ingestion.DocumentRejected, match="too much memory"):
        ingestion.extract_and_embed_pdf(b"%PDF-1.7")


def test_parser_limits_still_reach_the_user(monkeypatch):
    monkeypatch.setattr(ingestion, "extract_pages", fakes.reject)
    with pytest.raises(ingestion.DocumentRejected, match="900 pages"):
        ingestion.extract_and_embed_pdf(b"%PDF-1.7")
