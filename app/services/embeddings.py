from functools import lru_cache
from typing import List


@lru_cache(maxsize=1)
def _get_model():
    # Load model weights only when an embedding is requested.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    result = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return result.tolist()


def generate_single_embedding(text: str) -> List[float]:
    result = _get_model().encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return result[0].tolist()
