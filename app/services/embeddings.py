import threading
from typing import List

import numpy as np

# Every stored chunk records the model that embedded it. Vectors from
# different models are not comparable, so changing this requires
# re-embedding existing documents (retry processing on each of them).
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

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
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(EMBEDDING_MODEL)
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
    result = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return validate_vectors(result, len(texts)).tolist()


def generate_single_embedding(text: str) -> List[float]:
    return generate_embeddings([text])[0]
