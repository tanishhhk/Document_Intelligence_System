import os
import threading
from typing import List

import numpy as np

# Every stored chunk records the model that embedded it. Vectors from
# different models are not comparable, so changing this requires
# re-embedding existing documents (retry processing on each of them).
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
# The same model run with ONNX Runtime through fastembed: identical vectors
# (cosine 1.0 against sentence-transformers) at a fraction of PyTorch's memory,
# so the API fits a 512 MB host.
ONNX_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def model_cache_dir() -> str | None:
    """Where models are stored; the Docker image bakes them into FASTEMBED_CACHE_PATH."""
    return os.environ.get("FASTEMBED_CACHE_PATH") or None

_model = None
_model_lock = threading.Lock()


class EmbeddingError(RuntimeError):
    """The embedding model failed or returned unusable vectors."""


def _get_model():
    # Load weights only when needed, and only once even if the ingestion
    # worker and a request ask for the first embedding at the same time.
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(ONNX_MODEL, cache_dir=model_cache_dir())
    return _model


def validate_vectors(vectors, expected_count: int) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape != (expected_count, EMBEDDING_DIMENSION):
        raise EmbeddingError(
            f"Expected {expected_count} vectors of dimension {EMBEDDING_DIMENSION}, "
            f"got shape {matrix.shape}."
        )
    if not np.isfinite(matrix).all():
        raise EmbeddingError("The embedding model returned non-finite values.")
    if (np.linalg.norm(matrix, axis=1) == 0).any():
        raise EmbeddingError("The embedding model returned a zero vector.")
    return matrix


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    vectors = list(_get_model().embed(texts, batch_size=32))
    matrix = validate_vectors(vectors, len(texts))
    return (matrix / np.linalg.norm(matrix, axis=1, keepdims=True)).tolist()


def generate_single_embedding(text: str) -> List[float]:
    return generate_embeddings([text])[0]
