"""Checks for the in-process rate limiter, retry decorator, and safe-generate
fallback in app/core/resilience.py.

Run directly with no test framework installed:

    python test_resilience.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: pure/in-memory logic, no real sleeping (with_retry is called with
base_delay=0, and the rate limiter's window is exercised by rewriting its
internal timestamp list directly rather than sleeping past it) and no network.
Every caller of check_rate_limit (/run-agent, /check-conflicts,
/finalize-calendar, /auth/login) shares this same in-process dict per
CLAUDE.md, so a bug here is a bug on all of them at once.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.core.resilience as resilience
from app.core.resilience import check_rate_limit, safe_generate, with_retry

# ---- check_rate_limit -------------------------------------------------------


def test_requests_under_the_limit_are_allowed():
    key = "test:under-limit"
    for _ in range(5):
        assert check_rate_limit(key, max_requests=5, window_seconds=60)


def test_the_request_that_crosses_the_limit_is_refused():
    key = "test:crosses-limit"
    for _ in range(3):
        assert check_rate_limit(key, max_requests=3, window_seconds=60)
    assert not check_rate_limit(key, max_requests=3, window_seconds=60)


def test_limit_is_tracked_independently_per_key():
    # This is what lets /auth/login rate-limit per-IP and per-email
    # independently (see main.py::login_endpoint) rather than sharing a bucket.
    a, b = "test:key-a", "test:key-b"
    for _ in range(3):
        assert check_rate_limit(a, max_requests=3, window_seconds=60)
    assert not check_rate_limit(a, max_requests=3, window_seconds=60)
    # A different key must not be affected by key a's history.
    assert check_rate_limit(b, max_requests=3, window_seconds=60)


def test_requests_outside_the_window_no_longer_count():
    key = "test:window-expiry"
    for _ in range(3):
        assert check_rate_limit(key, max_requests=3, window_seconds=60)
    assert not check_rate_limit(key, max_requests=3, window_seconds=60)

    # Age every recorded timestamp out of the window instead of sleeping ΓÇö
    # same effect as real time passing, without a slow test.
    resilience._rate_limit_tracker[key] = [t - 61 for t in resilience._rate_limit_tracker[key]]
    assert check_rate_limit(key, max_requests=3, window_seconds=60)


def test_rate_limiter_resets_on_restart_is_an_in_process_dict():
    # Documents the known limitation from CLAUDE.md: this tracker is a plain
    # module-level dict, not backed by Redis/DB, so it resets on process
    # restart and is not shared across worker processes.
    assert isinstance(resilience._rate_limit_tracker, dict)


# ---- with_retry --------------------------------------------------------------


def test_with_retry_returns_the_result_on_eventual_success():
    calls = {"count": 0}

    @with_retry(max_retries=3, base_delay=0)
    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ValueError("not yet")
        return "ok"

    assert flaky() == "ok"
    assert calls["count"] == 3


def test_with_retry_raises_the_last_error_after_exhausting_attempts():
    calls = {"count": 0}

    @with_retry(max_retries=2, base_delay=0)
    def always_fails():
        calls["count"] += 1
        raise ValueError(f"attempt {calls['count']}")

    try:
        always_fails()
    except ValueError as err:
        assert "attempt 2" in str(err)
        assert calls["count"] == 2
    else:
        raise AssertionError("with_retry must re-raise after exhausting max_retries")


def test_with_retry_does_not_retry_a_function_that_succeeds_first_try():
    calls = {"count": 0}

    @with_retry(max_retries=5, base_delay=0)
    def succeeds():
        calls["count"] += 1
        return "fine"

    assert succeeds() == "fine"
    assert calls["count"] == 1


# ---- safe_generate -----------------------------------------------------------


def test_safe_generate_returns_the_function_result_on_success():
    assert safe_generate(lambda: "real answer") == "real answer"


def test_safe_generate_returns_the_fallback_on_exception():
    def boom():
        raise RuntimeError("LLM is down")

    assert safe_generate(boom) == "Service temporarily unavailable. Please try again shortly."


def test_safe_generate_accepts_a_custom_fallback_message():
    def boom():
        raise RuntimeError("LLM is down")

    assert safe_generate(boom, fallback_message="custom fallback") == "custom fallback"


def test_safe_generate_forwards_args_and_kwargs():
    def add(a, b, c=0):
        return a + b + c

    assert safe_generate(add, 1, 2, c=3) == 6


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  ok  {name}")
    print(f"\n{passed} checks passed")
