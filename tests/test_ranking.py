import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from app.config import settings
from app.services import ranking, reranker

TEXTS = [
    "General terms apply to every order placed with the company.",
    "Clause 7.2 sets the notice period at 30 days for either party.",
    "Payment is due within 45 days of the invoice date.",
]


def test_keywords_find_exact_terms_that_meaning_misses():
    dense = np.array([0.9, 0.2, 0.3])  # The embedding prefers the generic passage.
    assert ranking.rank("What does clause 7.2 say?", TEXTS, dense)[0] == 1


def test_bm25_ignores_stopwords_and_unknown_terms():
    assert ranking.bm25_scores("what is the", TEXTS).sum() == 0
    assert ranking.bm25_scores("invoice", TEXTS).argmax() == 2


def test_the_reranker_votes_but_does_not_overrule_alone():
    dense = np.array([0.1, 0.2, 0.9])
    order = ranking.rank("payment deadline", TEXTS, dense, rerank=lambda _q, texts: [0, 0, 0])
    assert order[0] == 2
    flipped = ranking.rank("payment", TEXTS, np.array([0.5, 0.5, 0.5]), rerank=lambda _q, t: [9, 0, 0])
    assert flipped[0] in (0, 2)


def test_a_failed_reranker_keeps_the_fused_order():
    dense = np.array([0.1, 0.9, 0.2])
    assert ranking.rank("notice", TEXTS, dense, rerank=lambda _q, _t: None) == ranking.rank("notice", TEXTS, dense)


def test_reranking_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "reranker_enabled", False)
    assert reranker.rerank("q", ["a"]) is None


@given(st.lists(st.text(max_size=80), min_size=1, max_size=30), st.text(max_size=40))
def test_ranking_is_always_a_permutation(texts, question):
    dense = np.linspace(0, 1, len(texts))
    order = ranking.rank(question, texts, dense, rerank=lambda _q, t: list(range(len(t))))
    assert sorted(order) == list(range(len(texts)))
