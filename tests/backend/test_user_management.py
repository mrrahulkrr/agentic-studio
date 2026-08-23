"""Checks for the last-developer lockout guard in app/main.py.

Run directly with no test framework installed:

    python test_user_management.py

Also written so `pytest` collects it unchanged, like test_auth.py.

Scope: `_refuse_if_last_developer` is the only thing standing between a
demote/delete call on /auth/users/{id} and locking every /admin/* and
/auth/users route out from under everyone, with no way back in short of
direct DB access and re-running seed_admin.py (see CLAUDE.md). It is pure
control flow over two already-tested DB functions
(get_user_by_id, count_developers), both imported by name into app.main's
namespace, so they're monkeypatched here the same way test_auth.py
monkeypatches auth.get_user_by_id — no live Postgres needed.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("API_SECRET_KEY", "test-secret-not-for-prod")

from fastapi import HTTPException

import app.main as main


class _Patcher:
    """Same tiny stand-in as test_auth.py's, so this runs with plain
    `python test_user_management.py` and no test framework installed."""

    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


def _stub_users(patch, users: dict[int, tuple], developer_count: int):
    patch.setattr(main, "get_user_by_id", lambda user_id: users.get(user_id))
    patch.setattr(main, "count_developers", lambda: developer_count)


def test_demoting_the_only_developer_is_refused():
    patch = _Patcher()
    try:
        _stub_users(patch, {1: (1, "dev@studio.com", "developer")}, developer_count=1)
        try:
            main._refuse_if_last_developer(1, "demote")
        except HTTPException as err:
            assert err.status_code == 400
            assert "developer" in err.detail.lower()
        else:
            raise AssertionError("demoting the last developer must be refused")
    finally:
        patch.undo()


def test_deleting_the_only_developer_is_refused():
    patch = _Patcher()
    try:
        _stub_users(patch, {1: (1, "dev@studio.com", "developer")}, developer_count=1)
        try:
            main._refuse_if_last_developer(1, "delete")
        except HTTPException as err:
            assert err.status_code == 400
        else:
            raise AssertionError("deleting the last developer must be refused")
    finally:
        patch.undo()


def test_demoting_one_of_several_developers_is_allowed():
    patch = _Patcher()
    try:
        _stub_users(patch, {1: (1, "dev@studio.com", "developer")}, developer_count=2)
        main._refuse_if_last_developer(1, "demote")  # must not raise
    finally:
        patch.undo()


def test_demoting_a_client_account_is_always_allowed_even_if_it_is_the_only_row():
    # count_developers()==0 here would be a nonsense state to guard against on
    # a client row; the check only fires for a target that is itself the last
    # developer, so a client account (index [2] != "developer") must pass
    # regardless of how many developers exist.
    patch = _Patcher()
    try:
        _stub_users(patch, {2: (2, "client@studio.com", "client")}, developer_count=0)
        main._refuse_if_last_developer(2, "demote")  # must not raise
    finally:
        patch.undo()


def test_acting_on_a_nonexistent_user_id_is_not_blocked_by_this_guard():
    # A 404 for a nonexistent id is main.py's job (the endpoint checks the
    # bool return of update_user_role/delete_user); this guard just must not
    # itself raise on a missing row.
    patch = _Patcher()
    try:
        _stub_users(patch, {}, developer_count=1)
        main._refuse_if_last_developer(999, "delete")  # must not raise
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
