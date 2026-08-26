"""Checks for the Calendar MCP -> service-account silent fallback in
app/main.py::_create_calendar_event.

Run directly with no test framework installed:

    python test_calendar_fallback.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: per CLAUDE.md, "CALENDAR_MODE=mcp tries the stdio MCP server ... and
silently falls back to the service-account path on any failure." No real MCP
subprocess or Google API call is made ΓÇö both calendar functions are
monkeypatched by name on app.main (they're imported directly into its
namespace), so this exercises only the fallback decision, not the
integrations themselves.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.main as main


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


async def _ok_mcp(summary, description, event_date):
    return "mcp-event-link"


async def _failing_mcp(summary, description, event_date):
    raise RuntimeError("npx @cocal/google-calendar-mcp could not be spawned")


async def _ok_service_account(summary, description, event_date):
    return "service-account-event-link"


def test_mcp_mode_uses_mcp_when_it_succeeds():
    patch = _Patcher()
    try:
        patch.setattr(main, "CALENDAR_MODE", "mcp")
        patch.setattr(main, "create_calendar_event_via_mcp", _ok_mcp)
        patch.setattr(main, "create_event_via_service_account", _ok_service_account)

        result = asyncio.run(main._create_calendar_event("Film", "desc", "2026-07-04"))
        assert result == "mcp-event-link"
    finally:
        patch.undo()


def test_mcp_failure_falls_back_to_service_account_silently():
    patch = _Patcher()
    try:
        patch.setattr(main, "CALENDAR_MODE", "mcp")
        patch.setattr(main, "create_calendar_event_via_mcp", _failing_mcp)
        patch.setattr(main, "create_event_via_service_account", _ok_service_account)

        # The whole point of the fallback: this must not raise even though
        # the MCP path failed.
        result = asyncio.run(main._create_calendar_event("Film", "desc", "2026-07-04"))
        assert result == "service-account-event-link"
    finally:
        patch.undo()


def test_service_account_failure_is_not_swallowed():
    # There is no further fallback past service_account ΓÇö its own exception
    # must propagate rather than being silently absorbed like the MCP one is.
    patch = _Patcher()
    try:
        patch.setattr(main, "CALENDAR_MODE", "service_account")

        async def _failing_service_account(summary, description, event_date):
            raise RuntimeError("Google API credentials invalid")

        patch.setattr(main, "create_event_via_service_account", _failing_service_account)

        try:
            asyncio.run(main._create_calendar_event("Film", "desc", "2026-07-04"))
        except RuntimeError as err:
            assert "credentials invalid" in str(err)
        else:
            raise AssertionError("a service-account failure with no fallback must propagate")
    finally:
        patch.undo()


def test_non_mcp_mode_never_calls_the_mcp_path_at_all():
    patch = _Patcher()
    try:
        called = {"mcp": False}

        async def _tracking_mcp(summary, description, event_date):
            called["mcp"] = True
            return "should not be reached"

        patch.setattr(main, "CALENDAR_MODE", "service_account")
        patch.setattr(main, "create_calendar_event_via_mcp", _tracking_mcp)
        patch.setattr(main, "create_event_via_service_account", _ok_service_account)

        result = asyncio.run(main._create_calendar_event("Film", "desc", "2026-07-04"))
        assert result == "service-account-event-link"
        assert called["mcp"] is False
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
