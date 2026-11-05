"""A small cross-encoder that reorders retrieved passages by reading each one
with the question. It runs on CPU in well under a second for 20 passages.

If the model cannot be loaded, retrieval carries on without it.
"""
import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"

_model = None
_unavailable = False
_lock = threading.Lock()


def _get_model():
    global _model, _unavailable
    if _model is None and not _unavailable:
        with _lock:
            if _model is None and not _unavailable:
                try:
                    from sentence_transformers import CrossEncoder

                    _model = CrossEncoder(RERANKER_MODEL, max_length=384)
                except Exception:
                    _unavailable = True
                    logger.warning("The re-ranker could not be loaded; ranking without it.")
    return _model


def rerank(question: str, texts: list[str]):
    """Relevance scores for each text, or None when re-ranking is off or unavailable."""
    if not settings.reranker_enabled or not texts:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        return model.predict([(question, text) for text in texts], show_progress_bar=False)
    except Exception:
        logger.warning("Re-ranking failed; using the fused ranking.")
        return None
