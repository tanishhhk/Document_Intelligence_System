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
