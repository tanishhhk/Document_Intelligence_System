"""Deterministic stand-ins for the embedding model and the PDF pipeline."""
from app.services.embeddings import EMBEDDING_DIMENSION
from app.utils.text_processor import Chunk


def vector(index: int) -> list[float]:
    """A unit vector along one axis, so similarity between them is 0 or 1."""
    values = [0.0] * EMBEDDING_DIMENSION
    values[index % EMBEDDING_DIMENSION] = 1.0
    return values


def indexed(*texts: str, page: int = 1):
    """A result shaped like ingestion.extract_and_embed_pdf."""
    chunks = [Chunk(text, page, page) for text in texts]
    return chunks, [vector(i) for i in range(len(texts))], page


# Module-level, so the isolated child process can import them.


def sleep_forever(*_args, **_kwargs):
    import time

    time.sleep(600)


def exit_abruptly(*_args, **_kwargs):
    import os

    os._exit(3)


def allocate(megabytes, **_kwargs):
    return len(bytearray(megabytes * 1024 * 1024))


def reject(*_args, **_kwargs):
    raise ValueError("PDF has 900 pages; the limit is 500.")


def fail_unexpectedly(*_args, **_kwargs):
    raise KeyError("parser bug")


def pages_of(text, **_kwargs):
    return [(1, text)]
