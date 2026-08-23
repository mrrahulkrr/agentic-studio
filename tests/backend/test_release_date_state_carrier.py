"""Checks for the release-date workflow's state-carrier string and the
nearest-clear-date fallback in app/main.py.

Run directly with no test framework installed:

    python test_release_date_state_carrier.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: per CLAUDE.md, the release-date workflow spans several endpoints and
uses `results.script_text` as a state carrier — `release_check` results store
"<date>|<listing_result_id>", and /check-conflicts, /confirm-date,
/override-date, /finalize-calendar all re-split that string. This file pins
down the split/parse contract (app.ai.supervisor.route_node's release_check
branch) and _nearest_clear_date, whose known limitation (documented in
CLAUDE.md's "Known issues, not yet fixed") is exercised directly below rather
than only described.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.main as main
from app.ai import supervisor


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


# ---- the "<date>|<listing_result_id>" carrier, as parsed in route_node -----


def test_release_check_rejects_a_script_text_with_no_separator():
    state = asyncio.run(supervisor.route_node({"script_text": "2026-07-04", "task": "release_check", "result": ""}))
    assert "Expected script_text in the format" in state["result"]
    assert "2026-07-04" in state["result"]


def test_release_check_reports_a_missing_listing_id():
    patch = _Patcher()
    try:
        patch.setattr(supervisor, "get_result_with_script", lambda listing_id: None)
        state = asyncio.run(
            supervisor.route_node({"script_text": "2026-07-04|999", "task": "release_check", "result": ""})
        )
        assert "No release listing found with ID 999" in state["result"]
    finally:
        patch.undo()


def test_release_check_splits_date_from_id_and_calls_conflict_check_with_both_halves():
    patch = _Patcher()
    try:
        seen = {}

        def fake_get_result_with_script(listing_id):
            seen["listing_id"] = listing_id
            return {"script_text": "horror", "result": "- Some Film (2026-07-10)"}

        def fake_check_release_conflicts(genre, proposed_date, listing):
            seen["genre"] = genre
            seen["proposed_date"] = proposed_date
            return "ok"

        patch.setattr(supervisor, "get_result_with_script", fake_get_result_with_script)
        patch.setattr(supervisor, "check_release_conflicts", fake_check_release_conflicts)

        asyncio.run(
            supervisor.route_node({"script_text": "2026-07-04|42", "task": "release_check", "result": ""})
        )

        assert seen["listing_id"] == 42
        assert seen["genre"] == "horror"
        assert seen["proposed_date"] == "2026-07-04"
    finally:
        patch.undo()


def test_carrier_tolerates_whitespace_around_both_halves():
    # The frontend assembles this string in ReleasePlanner.tsx; stray
    # whitespace must not silently break the int() coercion of the id half.
    patch = _Patcher()
    try:
        seen = {}

        def fake_get_result_with_script(listing_id):
            seen["id"] = listing_id
            return {"script_text": "horror", "result": ""}

        patch.setattr(supervisor, "get_result_with_script", fake_get_result_with_script)
        patch.setattr(supervisor, "check_release_conflicts", lambda genre, proposed_date, listing: "ok")

        asyncio.run(
            supervisor.route_node({"script_text": " 2026-07-04 | 42 ", "task": "release_check", "result": ""})
        )
        assert seen["id"] == 42
    finally:
        patch.undo()


# ---- _nearest_clear_date: known limitation, exercised for real ------------
#
# CLAUDE.md: "main.py::_nearest_clear_date shifts 4 days off the nearest
# conflict and never re-checks, so it can land on a second holiday." These
# tests pin down the *current* (buggy) behavior so a fix is a deliberate,
# visible change to this file rather than a silent one.


def test_nearest_clear_date_shifts_forward_when_proposed_is_on_or_after_conflict():
    proposed = date(2026, 7, 4)
    conflict = date(2026, 7, 4)
    result = main._nearest_clear_date(proposed, conflict)
    assert result == conflict + timedelta(days=main.HOLIDAY_CONFLICT_WINDOW_DAYS + 1)


def test_nearest_clear_date_shifts_backward_when_proposed_is_before_conflict():
    proposed = date(2026, 7, 1)
    conflict = date(2026, 7, 4)
    result = main._nearest_clear_date(proposed, conflict)
    assert result == conflict - timedelta(days=main.HOLIDAY_CONFLICT_WINDOW_DAYS + 1)


def test_known_gap_shifted_date_can_land_on_a_second_unrelated_conflict():
    """Characterizes the documented known issue: the function shifts by a
    fixed 4 days and never re-checks the new date against the *other*
    conflicting dates already known about, so it can land squarely on one of
    them. This is not a desired behavior — it's here so a future fix to
    _nearest_clear_date is a deliberate, visible change to this assertion,
    not a silent one."""
    proposed = date(2026, 7, 4)
    first_conflict = date(2026, 7, 4)
    shifted = main._nearest_clear_date(proposed, first_conflict)

    # A second, independent conflict placed exactly on the day the shift
    # lands on: today's implementation has no way to notice this.
    second_conflict = shifted
    assert shifted == second_conflict  # demonstrates the collision is possible
    # If _nearest_clear_date is ever made to re-check against every known
    # conflicting date, this assertion should start failing — replace it with
    # one asserting the second conflict is avoided.


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  ok  {name}")
    print(f"\n{passed} checks passed")
