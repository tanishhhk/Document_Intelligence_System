from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    # Load model weights only when an embedding is first requested. This keeps
    # API startup and route tests from triggering a model download unnecessarily.
    return SentenceTransformer("all-MiniLM-L6-v2")


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    embeddings = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return embeddings.tolist()


def generate_single_embedding(text: str) -> List[float]:
    embedding = _get_model().encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return embedding[0].tolist()
