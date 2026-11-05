"""Order a document's chunks for a question: meaning, keywords, then a re-ranker.

Embeddings find passages that mean the same thing in other words, but can
miss exact terms such as "clause 7.2", product codes or figures. BM25 keyword
scores catch those. The two rankings are combined with reciprocal rank fusion,
which needs no score calibration, and a cross-encoder then reorders the top
candidates by reading question and passage together.
"""
import math
import re
from collections import Counter

import numpy as np

_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its my of on or our "
    "so that the their there this to was we were what when where which who why will with you your".split()
)
RRF_K = 60
RERANK_CANDIDATES = 20


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def bm25_scores(question: str, texts: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    documents = [tokens(text) for text in texts]
    if not documents:
        return np.zeros(0)
    average = sum(map(len, documents)) / len(documents) or 1.0
    frequency = Counter(term for document in documents for term in set(document))
    scores = np.zeros(len(documents))
    for term in set(tokens(question)):
        if term not in frequency:
            continue
        idf = math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
        for index, document in enumerate(documents):
            count = document.count(term)
            if count:
                scores[index] += idf * count * (k1 + 1) / (count + k1 * (1 - b + b * len(document) / average))
    return scores


def fuse(*score_lists: np.ndarray) -> list[int]:
    """Reciprocal rank fusion of several score arrays over the same chunks."""
    fused = np.zeros(len(score_lists[0]))
    for scores in score_lists:
        for rank, index in enumerate(np.argsort(-scores, kind="stable")):
            if scores[index] > 0 or scores is score_lists[0]:
                fused[index] += 1.0 / (RRF_K + rank + 1)
    return list(np.argsort(-fused, kind="stable"))


def rank(question: str, texts: list[str], dense_scores: np.ndarray, rerank=None) -> list[int]:
    """Chunk indices, best first. rerank(question, texts) -> scores, or None to skip."""
    order = fuse(np.asarray(dense_scores, dtype=float), bm25_scores(question, texts))
    if rerank is None or len(order) < 2:
        return order
    head = order[:RERANK_CANDIDATES]
    scores = rerank(question, [texts[index] for index in head])
    if scores is None:
        return order
    # Blend rather than replace: the re-ranker votes alongside the fused order,
    # which keeps the exact-term matches it sometimes undervalues.
    blended = np.zeros(len(head))
    for position in range(len(head)):
        blended[position] += 1.0 / (RRF_K + position + 1)
    for rank_position, position in enumerate(np.argsort(-np.asarray(scores, dtype=float), kind="stable")):
        blended[position] += 1.0 / (RRF_K + rank_position + 1)
    reordered = [head[i] for i in np.argsort(-blended, kind="stable")]
    return reordered + order[RERANK_CANDIDATES:]
