from functools import lru_cache
from typing import List


@lru_cache(maxsize=1)
def _get_model():
    # Import the heavyweight ML runtime only when an embedding is actually
    # requested. API import and unit tests do not need to download model weights.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    embeddings = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return embeddings.tolist()


def generate_single_embedding(text: str) -> List[float]:
    embedding = _get_model().encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return embedding[0].tolist()
