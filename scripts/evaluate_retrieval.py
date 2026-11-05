"""Measure retrieval quality on the evaluation set in tests/eval/rag_dataset.py.

    python scripts/evaluate_retrieval.py

Compares the original fixed-size character chunker with the page-aware
chunker, using the real embedding model. For each answerable question:

- hit@k: every evidence string is contained in one of the top k chunks
- MRR: reciprocal rank of the first chunk containing the first evidence
- page@1: the top chunk's page range includes an expected page
  (page-aware chunker only; the character chunker has no page data)

It also reports the share of evidence strings that no chunk contains in
full, which happens when a chunk boundary cuts through them.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import generate_embeddings, generate_single_embedding  # noqa: E402
from app.utils.pdf_processor import extract_pages  # noqa: E402
from app.utils.text_processor import chunk_pages, chunk_text  # noqa: E402
from tests.eval.rag_dataset import DOCUMENTS, QUESTIONS, build_pdf  # noqa: E402


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _character_chunks(pages):
    text = "\n\n".join(page_text for _number, page_text in pages).strip()
    return [(chunk, None, None) for chunk in chunk_text(text)]


def _page_chunks(pages):
    return [(c.text, c.page_start, c.page_end) for c in chunk_pages(pages)]


STRATEGIES = {"character": _character_chunks, "page_aware": _page_chunks}


def evaluate(strategy):
    rows = []
    sizes = []
    split_evidence = total_evidence = 0
    for name in DOCUMENTS:
        pages = extract_pages(build_pdf(name))
        chunks = STRATEGIES[strategy](pages)
        sizes.extend(len(text) for text, _s, _e in chunks)
        texts = [_norm(text) for text, _s, _e in chunks]
        matrix = np.asarray(generate_embeddings([text for text, _s, _e in chunks]))

        for question in (q for q in QUESTIONS if q["document"] == name and q["evidence"]):
            evidence = [_norm(e) for e in question["evidence"]]
            for item in evidence:
                total_evidence += 1
                split_evidence += not any(item in text for text in texts)

            scores = matrix @ np.asarray(generate_single_embedding(question["question"]))
            order = list(np.argsort(-scores))
            first = next(
                (rank for rank, index in enumerate(order, start=1) if evidence[0] in texts[index]),
                None,
            )
            row = {
                "id": question["id"],
                "kind": question["kind"],
                "rr": 1.0 / first if first else 0.0,
            }
            for k in (1, 3):
                top = [texts[index] for index in order[:k]]
                row[f"hit@{k}"] = all(any(item in text for text in top) for item in evidence)
            _text, start, end = chunks[order[0]]
            if start is not None:
                row["page@1"] = any(start <= page <= end for page in question["pages"])
            rows.append(row)

    summary = {
        "strategy": strategy,
        "questions": len(rows),
        "chunks": len(sizes),
        "mean_chunk_chars": round(sum(sizes) / len(sizes)),
        "evidence_split_by_chunking": f"{split_evidence}/{total_evidence}",
        "hit@1": round(sum(r["hit@1"] for r in rows) / len(rows), 3),
        "hit@3": round(sum(r["hit@3"] for r in rows) / len(rows), 3),
        "mrr": round(sum(r["rr"] for r in rows) / len(rows), 3),
    }
    if "page@1" in rows[0]:
        summary["page@1"] = round(sum(r["page@1"] for r in rows) / len(rows), 3)
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row["hit@3"])
    summary["hit@3_by_kind"] = {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_kind.items())}
    summary["misses@3"] = [r["id"] for r in rows if not r["hit@3"]]
    return summary


if __name__ == "__main__":
    for name in STRATEGIES:
        print(json.dumps(evaluate(name), indent=2))
