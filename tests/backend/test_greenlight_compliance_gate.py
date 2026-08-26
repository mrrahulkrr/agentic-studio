"""Checks for app/ai/agents.py::check_compliance_structured ΓÇö the Greenlight
Committee's compliance gate, called from supervisor.py's gatekeeper_node.

Run directly with no test framework installed:

    python test_greenlight_compliance_gate.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: app.core.llm.generate_for_tier and app.data.retrieval.hybrid_search are
monkeypatched by name on app.ai.agents (imported directly into its
namespace), so this runs with no live Gemini call, no embedding call, and no
Postgres. guardrails.retrieval_status() itself is NOT patched ΓÇö it runs for
real, fed the same rerank_score shapes gemini_rerank actually produces (see
test_retrieval_pipeline.py), so this exercises the real integration between
retrieval_status()'s classification and check_compliance_structured's
branching on it.

Why this file exists: check_compliance_structured used to gate on the
legacy check_retrieval_confidence() boolean instead of retrieval_status(),
which meant a reranker outage (retrieval_status() == "unscored") and a
genuinely empty guidelines collection (retrieval_status() == "empty") were
indistinguishable ΓÇö both produced "message": "No guidelines found." with no
violations ever checked. That is exactly the bug class CLAUDE.md documents
as already fixed for check_compliance's prose report; it had reappeared,
unfixed, in this structured sibling used by the Greenlight Committee's
gatekeeper_node. This file pins down that "unscored" now gets its own
outcome, distinct from "empty", and that retrieved-but-unscored guidelines
still get checked for violations rather than being silently skipped.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.ai.agents as agents


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


def _fake_generate_text(*responses):
    """Returns `responses` in call order (repeating the last one past the end)
    and records every call, so a test can assert *how many times* the LLM was
    asked something ΓÇö specifically, that the violations prompt is skipped
    entirely for "empty"/"low_relevance" but not for "unscored".

    Stands in for generate_for_tier, not generate_text directly ΓÇö its first
    positional argument is the tier name ("FAST"/"STANDARD"), not the system
    prompt, since that's the wrapper every call site in agents.py now goes
    through (see llm.py::generate_for_tier)."""
    calls = []

    def _gen(tier, system_prompt, user_prompt, *args, **kwargs):
        calls.append((tier, system_prompt, user_prompt))
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    _gen.calls = calls
    return _gen


# ---- confident: the ordinary, fully-working path ---------------------------


def test_confident_matches_are_checked_for_violations():
    patch = _Patcher()
    try:
        fake = _fake_generate_text(
            "flagged: graphic violence",
            '{"hard_violations": ["sustained gun violence"], "soft_violations": []}',
        )
        patch.setattr(agents, "generate_for_tier", fake)
        patch.setattr(
            agents, "hybrid_search",
            lambda query, collection=None, top_k=3: [
                {"text": "no firearms discharged toward a named character", "rerank_score": 8.0},
            ],
        )

        result = agents.check_compliance_structured("INT. WAREHOUSE - NIGHT...")

        assert result["hard_violations"] == ["sustained gun violence"]
        assert result["soft_violations"] == []
        assert len(fake.calls) == 2, "confident matches must still be sent to the violations prompt"
    finally:
        patch.undo()


# ---- empty: nothing in the guidelines collection at all --------------------


def test_genuinely_empty_collection_returns_the_empty_message_without_checking_violations():
    patch = _Patcher()
    try:
        fake = _fake_generate_text("flagged: graphic violence")
        patch.setattr(agents, "generate_for_tier", fake)
        patch.setattr(agents, "hybrid_search", lambda query, collection=None, top_k=3: [])

        result = agents.check_compliance_structured("INT. WAREHOUSE - NIGHT...")

        assert result == {
            "hard_violations": [],
            "soft_violations": [],
            "message": "No guideline documents matched this content.",
        }
        # Only the flagged-topics call happened ΓÇö never asked to find violations
        # in guidelines it doesn't trust exist.
        assert len(fake.calls) == 1
    finally:
        patch.undo()


# ---- low_relevance: matches were found and scored, but none cleared the gate


def test_low_relevance_matches_return_a_manual_review_message_without_checking_violations():
    patch = _Patcher()
    try:
        fake = _fake_generate_text("flagged: graphic violence")
        patch.setattr(agents, "generate_for_tier", fake)
        patch.setattr(
            agents, "hybrid_search",
            lambda query, collection=None, top_k=3: [
                {"text": "unrelated catering guideline", "rerank_score": 1.5},
            ],
        )

        result = agents.check_compliance_structured("INT. WAREHOUSE - NIGHT...")

        assert result["hard_violations"] == []
        assert result["soft_violations"] == []
        assert "relevant enough" in result["message"]
        assert len(fake.calls) == 1
    finally:
        patch.undo()


# ---- unscored: the bug this file exists to pin down -------------------------


def test_reranker_failure_produces_unscored_not_empty_and_still_checks_the_retrieved_guidelines():
    """The regression: guideline_matches were retrieved (this is not an empty
    knowledge base) but the reranker failed, so every rerank_score is None ΓÇö
    exactly what gemini_rerank's own failure path produces. The old boolean
    gate (check_retrieval_confidence) treated this identically to "empty" and
    never even asked whether the retrieved text contained a violation."""
    patch = _Patcher()
    try:
        fake = _fake_generate_text(
            "flagged: minor in peril",
            '{"hard_violations": ["a minor shown unattended in physical jeopardy"], "soft_violations": []}',
        )
        patch.setattr(agents, "generate_for_tier", fake)
        patch.setattr(
            agents, "hybrid_search",
            lambda query, collection=None, top_k=3: [
                {"text": "6.4 A minor placed in physical jeopardy must not be shown unattended.", "rerank_score": None},
            ],
        )

        result = agents.check_compliance_structured("INT. FIRE ESCAPE - NIGHT...")

        # The retrieved (but unscored) guideline was actually checked, and its
        # violation surfaced ΓÇö the old gate would have returned [] here.
        assert result["hard_violations"] == ["a minor shown unattended in physical jeopardy"]
        assert len(fake.calls) == 2, "unscored matches must still be sent to the violations prompt"

        # And the caveat says *unscored*, not *empty* ΓÇö the two must not read
        # the same to whoever (or whatever, e.g. executive_agent) reads message.
        assert "unscored" in result["message"].lower()
        assert result["message"] != "No guideline documents matched this content."
    finally:
        patch.undo()


def test_unscored_outcome_is_distinguishable_from_a_genuinely_empty_collection():
    """Direct side-by-side: the two outcomes the original bug collapsed into
    one must now differ, both in whether violations were even checked and in
    the message text."""
    patch = _Patcher()
    try:
        patch.setattr(
            agents, "generate_for_tier",
            _fake_generate_text(
                "flagged: minor in peril",
                '{"hard_violations": ["a minor shown unattended"], "soft_violations": []}',
            ),
        )
        patch.setattr(
            agents, "hybrid_search",
            lambda query, collection=None, top_k=3: [
                {"text": "6.4 A minor placed in physical jeopardy...", "rerank_score": None},
            ],
        )
        unscored = agents.check_compliance_structured("script text")
    finally:
        patch.undo()

    patch = _Patcher()
    try:
        patch.setattr(agents, "generate_for_tier", _fake_generate_text("flagged: minor in peril"))
        patch.setattr(agents, "hybrid_search", lambda query, collection=None, top_k=3: [])
        empty = agents.check_compliance_structured("script text")
    finally:
        patch.undo()

    assert unscored["message"] != empty["message"]
    assert unscored["hard_violations"] != []
    assert empty["hard_violations"] == []


def test_parse_failure_after_unscored_retrieval_still_carries_the_unscored_caveat():
    patch = _Patcher()
    try:
        fake = _fake_generate_text("flagged: something", "not valid json at all")
        patch.setattr(agents, "generate_for_tier", fake)
        patch.setattr(
            agents, "hybrid_search",
            lambda query, collection=None, top_k=3: [{"text": "some guideline", "rerank_score": None}],
        )

        result = agents.check_compliance_structured("script text")

        assert result["hard_violations"] == []
        assert result["soft_violations"] == []
        assert "Failed to parse compliance" in result["message"]
        assert "unscored" in result["message"].lower()
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
