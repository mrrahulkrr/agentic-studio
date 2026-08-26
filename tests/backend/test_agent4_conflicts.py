"""Checks for Agent 4's date-conflict logic (microservices/agent4_service.py):
holiday lookups, hardcoded sporting/awards event windows, and the combined
report the A2A executor returns.

Run directly with no test framework installed:

    python test_agent4_conflicts.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: pure functions plus one HTTP call to date.nager.at, which is
monkeypatched out (`_fetch_holidays_for_year`) so this runs offline and
deterministically. Per CLAUDE.md's "Known issues, not yet fixed": "Sporting
and awards dates in agent4_service.py are hardcoded for 2026-2028 and will
rot silently" ΓÇö that gap is characterized directly below rather than only
described, the same way test_release_date_state_carrier.py does for
_nearest_clear_date.
"""

import sys
from pathlib import Path

# agent4_service.py adds backend/ to sys.path itself when run as a script, but
# importing it as a module here needs the same fixup done first. This file
# lives in tests/backend/, not backend/ itself (see tests/TEST_PLAN.md), so
# backend/ is found relative to the repo root rather than to this file.
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import microservices.agent4_service as agent4


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


_US_HOLIDAYS_2026 = [
    {"date": "2026-07-04", "name": "Independence Day"},
    {"date": "2026-12-25", "name": "Christmas Day"},
]


def _fake_fetch(by_year: dict[tuple[int, str], list[dict] | None]):
    def _fetch(year, country_code):
        return by_year.get((year, country_code), [])

    return _fetch


# ---- check_country_holidays --------------------------------------------------


def test_a_date_within_the_window_of_a_holiday_is_a_conflict():
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        patch.setattr(agent4, "_fetch_holidays_for_year", _fake_fetch({(2026, "US"): _US_HOLIDAYS_2026}))
        report = agent4.check_country_holidays("2026-07-05")
        assert report["US"]["conflict"] is True
        assert report["US"]["holiday_name"] == "Independence Day"
    finally:
        patch.undo()


def test_a_date_outside_the_window_is_not_a_conflict():
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        patch.setattr(agent4, "_fetch_holidays_for_year", _fake_fetch({(2026, "US"): _US_HOLIDAYS_2026}))
        report = agent4.check_country_holidays("2026-06-01")
        assert report["US"]["conflict"] is False
        assert report["US"]["holiday_date"] is None
    finally:
        patch.undo()


def test_window_boundary_is_inclusive_at_three_days():
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        patch.setattr(agent4, "_fetch_holidays_for_year", _fake_fetch({(2026, "US"): _US_HOLIDAYS_2026}))
        report = agent4.check_country_holidays("2026-07-07")  # exactly 3 days from 07-04
        assert report["US"]["conflict"] is True
        assert agent4.CONFLICT_WINDOW_DAYS == 3
    finally:
        patch.undo()


def test_a_failed_fetch_for_the_primary_year_is_reported_as_unknown_not_ok():
    """This is the one place a Nager API outage must not silently look like
    'no conflict' ΓÇö 'unknown' has to reach the caller distinguishably."""
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        patch.setattr(agent4, "_fetch_holidays_for_year", _fake_fetch({(2026, "US"): None}))
        report = agent4.check_country_holidays("2026-07-04")
        assert report["US"]["status"] == "unknown"
        assert report["US"]["conflict"] is None
    finally:
        patch.undo()


def test_year_boundary_also_checks_the_adjacent_year():
    # A date in early January must also check the previous year's holidays
    # (a conflict could be Dec 31 of the year before).
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        seen_years = []

        def fetch(year, country_code):
            seen_years.append(year)
            return []

        patch.setattr(agent4, "_fetch_holidays_for_year", fetch)
        agent4.check_country_holidays("2026-01-02")
        assert 2025 in seen_years and 2026 in seen_years
    finally:
        patch.undo()


# ---- check_global_event_conflicts: hardcoded sporting/awards dates --------


def test_finds_a_conflict_within_the_window_for_a_known_year():
    results = agent4.check_global_event_conflicts("2026-02-10", agent4.SPORTING_EVENTS)
    super_bowl = next(r for r in results if r["name"] == "Super Bowl")
    assert super_bowl["conflict"] is True
    assert super_bowl["date"] == "2026-02-08"


def test_no_conflict_far_from_any_hardcoded_date():
    results = agent4.check_global_event_conflicts("2026-06-01", agent4.SPORTING_EVENTS)
    assert all(not r["conflict"] for r in results)


def test_known_gap_a_year_with_no_hardcoded_entry_silently_uses_the_nearest_other_year():
    """Characterizes the documented known issue: 'Sporting and awards dates in
    agent4_service.py are hardcoded for 2026-2028 and will rot silently.'
    There is no explicit 'unknown year' case ΓÇö a date far outside the
    hardcoded range is just compared against whichever hardcoded year is
    numerically nearest, and reported as a normal (non-)conflict with no
    signal that the underlying date might not even be correct once real
    events are announced for that year. Pinning this down means a future fix
    (e.g. an explicit "date unknown for year 2031" case) is a deliberate,
    visible change to this assertion."""
    results = agent4.check_global_event_conflicts("2031-06-15", agent4.SPORTING_EVENTS)
    world_cup = next(r for r in results if r["name"] == "FIFA World Cup Final")
    # Nearest hardcoded date is 2030-07-21 (there is no 2031 entry at all) ΓÇö
    # the function has no way to say "I don't actually know 2031's date".
    assert world_cup["date"] == "2030-07-21"
    assert world_cup["days_away"] > 300


# ---- check_all_conflicts: the combined report the A2A executor returns ----


def test_combined_report_has_all_three_sections():
    patch = _Patcher()
    try:
        patch.setattr(agent4, "SUPPORTED_COUNTRIES", ["US"])
        patch.setattr(agent4, "_fetch_holidays_for_year", _fake_fetch({(2026, "US"): _US_HOLIDAYS_2026}))
        report = agent4.check_all_conflicts("2026-07-04")
        assert set(report.keys()) == {"holidays", "sporting_events", "awards_ceremonies"}
        assert "US" in report["holidays"]
        assert any(r["name"] == "Super Bowl" for r in report["sporting_events"])
        assert any(r["name"] == "Oscars" for r in report["awards_ceremonies"])
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
