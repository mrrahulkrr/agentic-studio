# ---------------------------------------------------------------------------
# Developer docs viewer — backend half.
#
# Mirrors how ADMIN_TABLES keeps generic SQL safe (app/data/database.py):
#   1. The only names ever accepted from a client are keys, checked against
#      DOC_REGISTRY below — never a path.
#   2. The path each key maps to is fixed here, at import time, not built
#      from anything in the request.
# Unlike ADMIN_TABLES this isn't a database concern at all — it's a plain
# filesystem read — so it lives in its own app/core module rather than next
# to the DB helpers in database.py, the same way auth.py and guardrails.py
# each get their own module instead of being folded into main.py.
#
# Read fresh on every request (see get_doc_text) — no cache, no read-at-
# import. These files are small and read infrequently (a developer opening
# a docs tab, not a hot path like /run-agent), and the entire point of this
# viewer is to never show a stale copy; caching would reintroduce that
# problem one layer down.
# ---------------------------------------------------------------------------

from pathlib import Path

# backend/ is this repo's declared working directory (see CLAUDE.md), but
# three of these five docs live above backend/ — so REPO_ROOT is computed
# from this file's own ancestry, not from cwd, and stays correct regardless
# of where the process was launched from.
# app/core/docs_registry.py -> app/core -> app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = REPO_ROOT / "backend"

DOC_REGISTRY: dict[str, dict] = {
    "readme": {
        "title": "README",
        "path": REPO_ROOT / "README.md",
    },
    "architecture": {
        "title": "Architecture",
        "path": _BACKEND_ROOT / "ARCHITECTURE.md",
    },
    "project-guide": {
        "title": "Project Guide",
        "path": REPO_ROOT / "PROJECT_GUIDE.md",
    },
    "testing-guide": {
        "title": "Testing Guide",
        "path": REPO_ROOT / "tests" / "TESTING_GUIDE.md",
    },
    "test-plan": {
        "title": "Test Plan",
        "path": REPO_ROOT / "tests" / "TEST_PLAN.md",
    },
}


def doc_summary() -> list[dict]:
    """What GET /admin/docs returns: key + title, no paths, no content."""
    return [{"key": key, "title": spec["title"]} for key, spec in DOC_REGISTRY.items()]


def get_doc_text(key: str) -> str | None:
    """Raw markdown for one registered key, read fresh from disk. None if the
    key isn't in DOC_REGISTRY — the caller turns that into a 404. `key` is
    only ever used as a dict lookup, never joined onto a path, so a value
    like "../../.env" simply isn't a registered key and gets the same None
    any other unknown key would."""
    spec = DOC_REGISTRY.get(key)
    if spec is None:
        return None
    return spec["path"].read_text(encoding="utf-8")
