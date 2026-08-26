"""Checks for the hybrid retrieval pipeline in app/data/retrieval.py: the
dense+BM25 blend and the reranker's failure mode.

Run directly with no test framework installed:

    python test_retrieval_pipeline.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: app.core.llm.generate_for_tier and app.data.database's search_similar /
bm25_search are monkeypatched by name on app.data.retrieval (imported
directly into its namespace), so this exercises the blend math and the
rerank-failure path with no live Gemini call, no embedding call, and no
Postgres. test_release_conflicts.py already pins down retrieval_status()
itself (the confidence gate); this file covers the pipeline that feeds it ΓÇö
specifically the reranker fallback described in retrieval.py's own docstring:
a failed reranker must set rerank_score to None, never back-fill it from
hybrid_score (that back-fill was a real bug: hybrid_score is 0.0-1.0 and can
never clear the 5.0 confidence threshold, so a reranker outage looked
identical to "no relevant guidelines found").

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.data.retrieval as retrieval


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


# ---- gemini_rerank: the bug this pipeline exists to prevent ----------------


def test_rerank_scores_are_attached_and_used_to_sort_descending():
    patch = _Patcher()
    try:
        patch.setattr(retrieval, "generate_for_tier", lambda *a, **k: '{"scores": [2, 9, 5]}')
        candidates = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        result = retrieval.gemini_rerank("query", candidates)
        assert [c["text"] for c in result] == ["b", "c", "a"]
        assert [c["rerank_score"] for c in result] == [9.0, 5.0, 2.0]
    finally:
        patch.undo()


def test_reranker_failure_sets_none_not_a_backfilled_hybrid_score():
    """The bug: a failed reranker used to write hybrid_score into
    rerank_score, which can never reach the 5.0 confidence threshold. None is
    the only correct output here."""
    patch = _Patcher()
    try:
        def boom(*a, **k):
            raise RuntimeError("Gemini is down")

        patch.setattr(retrieval, "generate_for_tier", boom)
        candidates = [{"text": "a", "hybrid_score": 0.95}, {"text": "b", "hybrid_score": 0.4}]
        result = retrieval.gemini_rerank("query", candidates)
        assert all(c["rerank_score"] is None for c in result)
        # And explicitly: not silently equal to hybrid_score.
        assert all(c["rerank_score"] != c["hybrid_score"] for c in result)
    finally:
        patch.undo()


def test_reranker_returning_the_wrong_number_of_scores_is_treated_as_failure():
    patch = _Patcher()
    try:
        # Two candidates, one score ΓÇö must not raise out of gemini_rerank.
        patch.setattr(retrieval, "generate_for_tier", lambda *a, **k: '{"scores": [7]}')
        candidates = [{"text": "a"}, {"text": "b"}]
        result = retrieval.gemini_rerank("query", candidates)
        assert all(c["rerank_score"] is None for c in result)
    finally:
        patch.undo()


def test_reranker_returning_unparseable_json_is_treated_as_failure():
    patch = _Patcher()
    try:
        patch.setattr(retrieval, "generate_for_tier", lambda *a, **k: "not json at all")
        candidates = [{"text": "a"}]
        result = retrieval.gemini_rerank("query", candidates)
        assert result[0]["rerank_score"] is None
    finally:
        patch.undo()


def test_empty_candidate_list_is_returned_untouched():
    assert retrieval.gemini_rerank("query", []) == []


# ---- hybrid_search: the 0.6/0.4 max-normalized blend -----------------------


def test_hybrid_search_blends_dense_and_bm25_and_reranks():
    patch = _Patcher()
    try:
        patch.setattr(retrieval, "embed_text", lambda q: [0.0] * 768)
        patch.setattr(
            retrieval, "search_similar",
            lambda embedding, collection=None, top_k=8: [
                {"text": "dense-only", "metadata": {}, "distance": 0.1},   # dense_score 0.9
                {"text": "shared", "metadata": {}, "distance": 0.5},       # dense_score 0.5
            ],
        )
        patch.setattr(
            retrieval, "bm25_search",
            lambda query, collection=None, top_k=8: [
                {"text": "shared", "metadata": {}, "bm25_score": 10.0},
                {"text": "bm25-only", "metadata": {}, "bm25_score": 5.0},
            ],
        )
        # Deterministic "reranker": keep hybrid order, just attach a score.
        patch.setattr(
            retrieval, "gemini_rerank",
            lambda query, candidates: sorted(candidates, key=lambda c: c["hybrid_score"], reverse=True),
        )

        results = retrieval.hybrid_search("query", collection="guidelines", top_k=3)
        texts = {r["text"] for r in results}
        assert texts == {"dense-only", "shared", "bm25-only"}
        # "shared" appears in both dense and bm25 results and must have both
        # scores populated, not just whichever source it was seen in last.
        shared = next(r for r in results if r["text"] == "shared")
        assert shared["dense_score"] == 0.5
        assert shared["bm25_score"] == 10.0
    finally:
        patch.undo()


def test_hybrid_search_returns_empty_when_nothing_is_found_in_either_source():
    patch = _Patcher()
    try:
        patch.setattr(retrieval, "embed_text", lambda q: [0.0] * 768)
        patch.setattr(retrieval, "search_similar", lambda embedding, collection=None, top_k=8: [])
        patch.setattr(retrieval, "bm25_search", lambda query, collection=None, top_k=8: [])
        assert retrieval.hybrid_search("query") == []
    finally:
        patch.undo()


def test_hybrid_search_respects_top_k_after_reranking():
    patch = _Patcher()
    try:
        patch.setattr(retrieval, "embed_text", lambda q: [0.0] * 768)
        patch.setattr(
            retrieval, "search_similar",
            lambda embedding, collection=None, top_k=8: [
                {"text": f"doc-{i}", "metadata": {}, "distance": 0.1 * i} for i in range(5)
            ],
        )
        patch.setattr(retrieval, "bm25_search", lambda query, collection=None, top_k=8: [])
        patch.setattr(
            retrieval, "gemini_rerank",
            lambda query, candidates: sorted(candidates, key=lambda c: c["hybrid_score"], reverse=True),
        )
        results = retrieval.hybrid_search("query", top_k=2)
        assert len(results) == 2
    finally:
        patch.undo()


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  ok  {name}")
    print(f"\n{passed} checks passed")
