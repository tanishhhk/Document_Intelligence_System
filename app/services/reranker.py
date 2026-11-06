"""A small cross-encoder that reorders retrieved passages by reading each one
with the question. It runs on CPU in well under a second for 20 passages.

If the model cannot be loaded, retrieval carries on without it.
"""
import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

# The ms-marco MiniLM cross-encoder exported to ONNX, run by fastembed.
RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

_model = None
_unavailable = False
_lock = threading.Lock()


def _get_model():
    global _model, _unavailable
    if _model is None and not _unavailable:
        with _lock:
            if _model is None and not _unavailable:
                try:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    from app.services.embeddings import model_cache_dir

                    _model = TextCrossEncoder(RERANKER_MODEL, cache_dir=model_cache_dir())
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
        return list(model.rerank(question, texts))
    except Exception:
        logger.warning("Re-ranking failed; using the fused ranking.")
        return None
