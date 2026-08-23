"""Checks for the Gemini quota-exhaustion fallback: llm.py's 429/
RESOURCE_EXHAUSTED detection (Known Limitation #12), the GeminiQuotaExhausted
exception's tier attachment across call sites, and main.py's /run-agent
override validation + structured 429 payload.

Run directly with no test framework installed:

    python test_quota_fallback.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: llm.py's own Gemini SDK client (`_client`) is monkeypatched by name on
app.core.llm, so generate_text's 429/503 detection is exercised with no live
Gemini call. For the tier-attachment checks, llm.generate_text itself is
monkeypatched (not generate_for_tier, and not each call site's own import of
it) so the real generate_for_tier wrapper and the real call sites in
agents.py/ingest.py/retrieval.py/evaluator.py all run unmodified — this is
what actually confirms the wrapper is wired into those call sites, not just
that the wrapper works in isolation. app.main is imported directly, matching
test_user_management.py/test_calendar_fallback.py/
test_release_date_state_carrier.py's existing precedent (main.py's
module-level init_tables() call needs a reachable DATABASE_URL, same as
those files already require). _validate_model_overrides and
_quota_exhausted_payload are pure functions with no DB/LLM call of their own
either way.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.core.llm as llm
import app.ai.agents as agents
import app.ai.evaluator as evaluator
import app.data.ingest as ingest
import app.data.retrieval as retrieval
import app.main as main
from fastapi import HTTPException


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


# ---- generate_text's own 429 detection (Known Limitation #12) --------------


class _FakeModels:
    """Stands in for the real google-genai client's `.models`, whatever
    exception `side_effect` raises stringifies the same way the SDK's own
    RESOURCE_EXHAUSTED/UNAVAILABLE errors do — generate_text only inspects
    str(exc), it doesn't check exception type."""

    def __init__(self, side_effect):
        self.side_effect = side_effect
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        raise self.side_effect


class _FakeClient:
    def __init__(self, side_effect):
        self.models = _FakeModels(side_effect)


def test_a_429_response_raises_quota_exhausted_carrying_the_model_that_failed():
    patch = _Patcher()
    try:
        fake_client = _FakeClient(RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded for GenerateContent"))
        patch.setattr(llm, "_client", fake_client)
        try:
            llm.generate_text("system", "prompt", model="gemini-3.5-flash-lite")
            assert False, "expected GeminiQuotaExhausted"
        except llm.GeminiQuotaExhausted as exc:
            assert exc.model == "gemini-3.5-flash-lite"
    finally:
        patch.undo()


def test_a_429_response_is_never_retried():
    """Unlike 503 below: a retry can't out-wait a daily quota reset within
    one request's lifetime, so retrying would just waste the retry budget."""
    patch = _Patcher()
    try:
        fake_client = _FakeClient(RuntimeError("429 RESOURCE_EXHAUSTED"))
        patch.setattr(llm, "_client", fake_client)
        try:
            llm.generate_text("system", "prompt", model="gemini-3.5-flash", max_retries=3)
        except llm.GeminiQuotaExhausted:
            pass
        assert fake_client.models.calls == 1
    finally:
        patch.undo()


def test_a_429_response_never_falls_through_to_the_generic_fallback_string():
    """The bug this exists to prevent: the fallback string reads like a real
    (if apologetic) answer, which would hide that this specific call can't
    succeed against this model today."""
    patch = _Patcher()
    try:
        fake_client = _FakeClient(RuntimeError("429 RESOURCE_EXHAUSTED"))
        patch.setattr(llm, "_client", fake_client)
        raised = False
        try:
            result = llm.generate_text("system", "prompt")
            assert result != "I'm having trouble generating a response right now. Please try again."
        except llm.GeminiQuotaExhausted:
            raised = True
        assert raised, "must raise, not return a fallback string"
    finally:
        patch.undo()


def test_a_bare_RESOURCE_EXHAUSTED_message_with_no_429_substring_is_still_caught():
    patch = _Patcher()
    try:
        fake_client = _FakeClient(RuntimeError("RESOURCE_EXHAUSTED"))
        patch.setattr(llm, "_client", fake_client)
        try:
            llm.generate_text("system", "prompt", model="gemini-3.7-flash")
            assert False, "expected GeminiQuotaExhausted"
        except llm.GeminiQuotaExhausted as exc:
            assert exc.model == "gemini-3.7-flash"
    finally:
        patch.undo()


# ---- regression: 503/UNAVAILABLE must behave exactly as before -------------


def test_a_503_response_still_retries_and_still_falls_back_to_the_generic_string():
    """This task changed handling for 429/RESOURCE_EXHAUSTED only — 503's
    existing retry-then-fallback behavior must be untouched."""
    patch = _Patcher()
    try:
        fake_client = _FakeClient(RuntimeError("503 UNAVAILABLE: model overloaded"))
        patch.setattr(llm, "_client", fake_client)
        # max_retries=2 keeps this test's one real sleep (2**0 = 1s) short.
        result = llm.generate_text("system", "prompt", model="gemini-3.5-flash", max_retries=2)
        assert result == "I'm having trouble generating a response right now. Please try again."
        assert fake_client.models.calls == 2, "503 must still be retried up to max_retries"
    finally:
        patch.undo()


def test_an_unrecognized_failure_still_propagates_unchanged():
    patch = _Patcher()
    try:
        fake_client = _FakeClient(ValueError("something else entirely"))
        patch.setattr(llm, "_client", fake_client)
        try:
            llm.generate_text("system", "prompt")
            assert False, "expected the original exception to propagate"
        except llm.GeminiQuotaExhausted:
            assert False, "an unrelated failure must not be reported as quota exhaustion"
        except ValueError:
            pass
    finally:
        patch.undo()


# ---- generate_for_tier: tier attachment at real call sites, not just in ----
# ---- isolation — at least two different tiers, per two different files ----


def _fake_quota_generate_text(system_prompt, user_prompt, model=None, **kwargs):
    """Stands in for llm.generate_text itself (not generate_for_tier), so
    every real call site's own generate_for_tier call runs for real and is
    what attaches `tier` — this is what actually proves the wrapper is wired
    into agents.py/ingest.py, not just that it works when called directly."""
    raise llm.GeminiQuotaExhausted(model or "unknown-model", RuntimeError("429 simulated"))


def test_executive_agent_call_site_attaches_the_quality_tier():
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        try:
            agents.executive_agent({}, {}, {}, {})
            assert False, "expected GeminiQuotaExhausted to propagate"
        except llm.GeminiQuotaExhausted as exc:
            assert exc.tier == "QUALITY"
    finally:
        patch.undo()


def test_classify_chunk_call_site_attaches_the_fast_tier():
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        try:
            ingest.classify_chunk("some chunk of guideline text")
            assert False, "expected GeminiQuotaExhausted to propagate"
        except llm.GeminiQuotaExhausted as exc:
            assert exc.tier == "FAST"
    finally:
        patch.undo()


def test_generate_script_digest_call_site_attaches_the_standard_tier():
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        try:
            agents.generate_script_digest("a script")
            assert False, "expected GeminiQuotaExhausted to propagate"
        except llm.GeminiQuotaExhausted as exc:
            assert exc.tier == "STANDARD"
    finally:
        patch.undo()


# ---- call sites with a pre-existing degrade-gracefully contract must keep -
# ---- swallowing quota exhaustion exactly as they swallow any other failure


def test_gemini_rerank_degrades_to_unscored_on_quota_exhaustion_rather_than_propagating():
    """gemini_rerank's existing contract is to degrade to rerank_score=None
    on ANY failure (bad JSON, wrong array length, a down model) rather than
    fail the whole retrieval. Quota exhaustion — the highest-volume tier's
    most likely failure — is just one more reason that contract already
    exists for, not a new exception carved out of it."""
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        candidates = [{"text": "a"}, {"text": "b"}]
        result = retrieval.gemini_rerank("query", candidates)
        assert all(c["rerank_score"] is None for c in result)
    finally:
        patch.undo()


def test_score_faithfulness_degrades_to_a_none_scored_result_on_quota_exhaustion():
    """An optional eval score failing must never look like the primary
    answer failed. score_faithfulness's contract (unchanged): any failure,
    quota included, returns EvalResult(score=None, ...) instead of raising —
    otherwise main.py's /run-agent would discard an already-successful
    result just because the bonus score couldn't be computed."""
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        result = evaluator.score_faithfulness("script text", "some agent result")
        assert result.score is None
    finally:
        patch.undo()


def test_check_compliance_flag_topics_call_degrades_via_safe_generate():
    """agents.check_compliance's first pass goes through safe_generate,
    whose own contract (unchanged) is to swallow any exception into a
    fallback string — quota exhaustion included."""
    patch = _Patcher()
    try:
        patch.setattr(llm, "generate_text", _fake_quota_generate_text)
        patch.setattr(agents, "hybrid_search", lambda *a, **k: [])
        result = agents.check_compliance("INT. WAREHOUSE - NIGHT. A scene.")
        # Falls through to the "empty" retrieval_status branch — the point
        # here is only that no exception escaped check_compliance itself.
        assert isinstance(result, str)
    finally:
        patch.undo()


# ---- main.py: override validation ------------------------------------------


def test_a_valid_override_for_every_tier_is_honored():
    result = main._validate_model_overrides(
        '{"FAST": "gemini-2.5-flash-lite", "STANDARD": "gemini-3.6-flash", "QUALITY": "gemini-2.5-pro"}'
    )
    assert result == {
        "FAST": "gemini-2.5-flash-lite",
        "STANDARD": "gemini-3.6-flash",
        "QUALITY": "gemini-2.5-pro",
    }


def test_empty_string_means_no_overrides():
    assert main._validate_model_overrides("") == {}


def test_an_unknown_tier_is_rejected():
    try:
        main._validate_model_overrides('{"SLOW": "gemini-2.5-pro"}')
        assert False, "expected a 400"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "SLOW" in exc.detail


def test_a_model_not_on_that_tiers_candidate_list_is_rejected():
    try:
        # gemini-2.5-pro is a real, free model — just not an approved FAST
        # candidate. Must not be silently passed through to the Gemini API.
        main._validate_model_overrides('{"FAST": "gemini-2.5-pro"}')
        assert False, "expected a 400"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "gemini-2.5-pro" in exc.detail


def test_malformed_json_is_rejected_not_silently_ignored():
    try:
        main._validate_model_overrides("{not valid json")
        assert False, "expected a 400"
    except HTTPException as exc:
        assert exc.status_code == 400


def test_a_json_array_instead_of_an_object_is_rejected():
    try:
        main._validate_model_overrides('["gemini-3.5-flash-lite"]')
        assert False, "expected a 400"
    except HTTPException as exc:
        assert exc.status_code == 400


# ---- main.py: the structured 429 payload -----------------------------------


def test_quota_exhausted_payload_has_the_approved_shape():
    exc = llm.GeminiQuotaExhausted("gemini-3.5-flash-lite", RuntimeError("429"))
    exc.tier = "FAST"

    payload = main._quota_exhausted_payload(exc)

    assert payload["error_type"] == "gemini_quota_exhausted"
    assert payload["tier"] == "FAST"
    assert payload["tier_label"] == "Quick checks"
    assert payload["model_that_failed"] == "gemini-3.5-flash-lite"
    assert "usage limit" in payload["message"]
    # The failed model itself must not be offered back as an "alternative".
    alt_models = [a["model"] for a in payload["alternatives"]]
    assert "gemini-3.5-flash-lite" not in alt_models
    assert "gemini-2.5-flash-lite" in alt_models
    # Every alternative carries the plain-language description, not just a name.
    assert all(a["description"] for a in payload["alternatives"])


def test_quota_exhausted_payload_reads_the_right_tier_label_for_each_tier():
    for tier, label in (("FAST", "Quick checks"), ("STANDARD", "Everyday reports"), ("QUALITY", "Final judgment")):
        exc = llm.GeminiQuotaExhausted("some-model", RuntimeError("429"))
        exc.tier = tier
        assert main._quota_exhausted_payload(exc)["tier_label"] == label


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  ok  {name}")
    print(f"\n{passed} checks passed")
