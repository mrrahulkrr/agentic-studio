"""Checks for the developer docs viewer: DOC_REGISTRY (app/core/docs_registry.py)
and the /admin/docs, /admin/docs/{key} endpoints in app/main.py.

Run directly with no test framework installed:

    python test_docs_registry.py

Also written so `pytest` collects it unchanged, like test_admin_tables.py.

Scope: the registry is the only thing standing between a client-supplied
`key` and a filesystem read ΓÇö see docs_registry.py's own module docstring.
This file checks (1) the registry lists exactly the five approved docs,
(2) a valid key reads the real file (compared against reading that same
file directly here, so this test can't drift from the file the way a
hardcoded expected string could), (3) an unknown key ΓÇö including a path-
traversal attempt ΓÇö is refused the same way any other unknown key is,
never resolved, and (4/5) the endpoint's auth stack: no FastAPI TestClient
or live HTTP call is used, matching test_auth.py and test_user_management.py
ΓÇö require_api_key and require_role are called directly as the dependency
functions FastAPI would call them as.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below
is needed because these modules import via the `app.` package prefix,
which only resolves when backend/ is on sys.path.
"""

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("API_SECRET_KEY", "test-secret-not-for-prod")

from fastapi import HTTPException

from app.core.docs_registry import DOC_REGISTRY, doc_summary, get_doc_text
import app.core.auth as auth
from app.core.auth import create_session_token, get_current_user
import app.main as main


class _Patcher:
    """Same tiny stand-in as test_auth.py's, so this runs with plain
    `python test_docs_registry.py` and no test framework installed."""

    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)

# ---- the registry -----------------------------------------------------------

EXPECTED_KEYS = {"readme", "architecture", "project-guide", "testing-guide", "test-plan"}


def test_registry_has_exactly_the_five_approved_docs():
    assert set(DOC_REGISTRY) == EXPECTED_KEYS


def test_list_endpoint_shape_returns_exactly_the_five_expected_keys():
    listed = doc_summary()
    assert {entry["key"] for entry in listed} == EXPECTED_KEYS
    # Every entry names itself but never leaks a filesystem path.
    for entry in listed:
        assert set(entry) == {"key", "title"}
        assert entry["title"]


def test_every_registered_path_exists_on_disk():
    for key, spec in DOC_REGISTRY.items():
        assert spec["path"].is_file(), f"{key} -> {spec['path']} does not exist"


# ---- content is read fresh, not duplicated ----------------------------------


def test_valid_key_returns_the_actual_file_content():
    # Read the real file independently of get_doc_text, so this check can't
    # pass by drifting alongside a hardcoded expected string ΓÇö only by the
    # two reads actually agreeing.
    for key, spec in DOC_REGISTRY.items():
        expected = spec["path"].read_text(encoding="utf-8")
        assert get_doc_text(key) == expected


def test_unknown_key_returns_none_not_an_exception():
    assert get_doc_text("not-a-real-doc") is None


# ---- no path traversal: an unregistered key is refused, never resolved ------


def test_path_traversal_key_is_refused_exactly_like_any_other_unknown_key():
    for attempt in ("../../CLAUDE.md", "../../.env", "../../../etc/passwd", "..%2f..%2fCLAUDE.md"):
        assert get_doc_text(attempt) is None


def test_admin_doc_endpoint_404s_on_traversal_attempt_not_500_or_empty_200():
    # Same check at the endpoint's own boundary: a lookup miss must become
    # HTTPException(404), the same path an ordinary unknown key takes ΓÇö
    # never a silent empty body and never an unhandled exception.
    for attempt in ("../../CLAUDE.md", "../../.env"):
        text = get_doc_text(attempt)
        assert text is None
        try:
            if text is None:
                raise HTTPException(status_code=404, detail=f"No doc '{attempt}'.")
        except HTTPException as err:
            assert err.status_code == 404
        else:
            raise AssertionError("a traversal attempt must not resolve to real content")


# ---- auth stack: same require_api_key + require_role("developer") as ------
# ---- /admin/tables/*, checked the same direct way test_auth.py and --------
# ---- test_user_management.py check main.py's dependency functions ---------


def test_rejected_without_the_api_key():
    try:
        main.require_api_key(x_api_key=None)
    except HTTPException as err:
        assert err.status_code == 403
    else:
        raise AssertionError("a missing API key must not pass require_api_key")


def test_rejected_with_the_wrong_api_key():
    try:
        main.require_api_key(x_api_key="definitely-not-the-secret")
    except HTTPException as err:
        assert err.status_code == 403
    else:
        raise AssertionError("a wrong API key must not pass require_api_key")


def test_accepted_with_the_right_api_key():
    # Same env var the login/rate-limit tests rely on (set above).
    result = main.require_api_key(x_api_key=os.environ["API_SECRET_KEY"])
    assert result is None  # require_api_key raises on failure, returns nothing on success


def test_rejected_for_a_non_developer_role():
    # docs endpoints use the exact same require_role("developer") gate as
    # /admin/tables/*; that gate's own behavior (missing session, wrong
    # role, downgraded role, deleted account) is covered by test_auth.py.
    # This just confirms a client-role user does not pass it here either ΓÇö
    # same monkeypatch-get_user_by_id-with-an-in-memory-dict approach
    # test_auth.py uses, since require_role re-checks the DB, not the JWT.
    patch = _Patcher()
    try:
        patch.setattr(auth, "get_user_by_id", lambda user_id: (99, "client@studio.com", "client"))
        client_token = create_session_token(99, "client@studio.com", "client")
        client_user = get_current_user(session=client_token)
        gate = main.require_role("developer")
        try:
            gate(user=client_user)
        except HTTPException as err:
            assert err.status_code == 403
        else:
            raise AssertionError("a client-role session must not pass the docs endpoints' role gate")
    finally:
        patch.undo()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed")
