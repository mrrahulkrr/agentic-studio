# Testing Guide

A practical, step-by-step guide to running, reading, and extending the test
suite. For *why* each file exists and what it covers, see
[`TEST_PLAN.md`](TEST_PLAN.md) in this same directory ΓÇö this guide is the
*how*.

There is no CI (see `CLAUDE.md`) and no test framework ΓÇö every check is a
plain `assert` in a `__main__` block. This is a deliberate convention, not
an oversight: running a test is `python some_file.py`, full stop, with
nothing to install first. Keep that property when adding to the suite.

---

## 1. What you need installed

- **Python**, with the backend's dependencies already installed (`pip
  install -r backend/requirements.txt`, or use the repo's `venv/` if you set
  one up per `CLAUDE.md`). The backend tests import real backend modules
  (`app.core.auth`, `app.data.database`, ΓÇª), just with network/DB calls
  monkeypatched out ΓÇö they still need the packages those modules import at
  module load time (FastAPI, psycopg2, etc.).
- **Node.js ΓëÑ 22.6** for the one frontend test file ΓÇö that version is the
  first to strip TypeScript types natively, so `node demo.test.ts` runs the
  `.ts` file directly with no build step and nothing extra installed.
- No pytest, no vitest, no Jest, nothing else. If a step in `run_tests.sh`
  needs `npm run lint` / `npx tsc --noEmit` / `npm run build`, that's each
  frontend app's own existing tooling (already a project dependency), not
  something added for testing.

No database, no live Gemini key, no Google Calendar credentials, and no
running Agent 4 / main API server are required to run the suite. Every test
that would otherwise need one of those monkeypatches the specific function
that would call out ΓÇö see the "Scope" note in each file's docstring for
exactly what's faked and what's real.

## 2. Running everything

From the repo root:

```bash
./run_tests.sh
```

This runs, in order: every `tests/backend/test_*.py`, then
`tests/frontend/demo.test.ts`, then `npm run lint` / `npx tsc --noEmit` /
`npm run build` for **both** `frontend/apps/client` and
`frontend/apps/admin` (they're independent installs, so each app's checks
run separately). It prints a `PASS`/`FAIL` line per step, a summary count at
the end, and **exits non-zero if anything failed** ΓÇö safe to use as a gate
before committing.

Narrower modes, when you don't want to wait on the frontend build:

```bash
./run_tests.sh --backend    # only tests/backend/test_*.py
./run_tests.sh --frontend   # demo.test.ts + lint/tsc/build for both apps
./run_tests.sh --unit       # backend + demo.test.ts, skip lint/tsc/build (fastest full pass)
```

`--unit` is the one to reach for while iterating on backend or shared
frontend logic ΓÇö it's the whole plain-assert suite with none of the slower
Next.js tooling.

## 3. Running a single file

Useful when you're working on one thing and don't want the whole suite's
output. Backend files need `backend/` importable, which each file arranges
itself (see ┬º5), so you can run them from anywhere by path, or from inside
`tests/backend/`:

```bash
# from the repo root
python tests/backend/test_auth.py

# or from inside the folder
cd tests/backend
python test_auth.py           # any Python with backend/requirements.txt installed
../../venv/Scripts/python.exe test_auth.py   # Windows venv, if that's what you use
```

```bash
cd tests/frontend
node --experimental-strip-types demo.test.ts
```

Each file prints one `ok  test_name` line per check as it runs, then a
final `N checks passed` line, and exits `0`. A failure prints the assertion
that broke (with Python's normal traceback, or Node's `AssertionError` for
the frontend file) and exits non-zero ΓÇö `run_tests.sh` treats any non-zero
exit as `FAIL` for that step.

## 4. Reading a failure

- **A backend `AssertionError`** names the exact `assert` line. Most files
  build small, explicit fixtures right above each `test_*` function, so the
  fastest read is: find the function named in the traceback, look at the
  fixture a few lines above it, and compare it to what the assert expected.
- **An `ImportError` / `ModuleNotFoundError` for `app.*`** almost always
  means the `sys.path` fixup at the top of the file didn't run yet, or you
  copied a test file out of `tests/backend/` without keeping that fixup ΓÇö
  see ┬º5.
- **A monkeypatch that silently "worked" but nothing changed** ΓÇö check that
  the patched name matches how the target module imports it. Several files
  patch a function *by name on the importing module* (e.g. patching
  `app.main.get_user_by_id` rather than `app.data.database.get_user_by_id`),
  because that's how `app.main` actually holds the reference after `from
  app.data.database import get_user_by_id`. Patching the wrong module is a
  common way to write a test that always passes for the wrong reason.
- **`demo.test.ts` throwing on import** ΓÇö check the three relative imports
  at the top (`../../frontend/packages/core/lib/...`) still resolve; they're
  relative to `tests/frontend/`, not to `frontend/packages/core/lib/` where
  the file used to live.

## 5. Why backend tests aren't run with a `cd` trick, and what to copy for a new file

Per `CLAUDE.md`, every backend module imports via the `app.` package prefix
(`from app.core.config import ...`), which only resolves when `backend/` is
on `sys.path`. `tests/backend/*.py` files are **not** inside `backend/`
anymore, so each one adds `backend/`'s absolute path to `sys.path` itself,
at the top of the file, before importing anything from `app`:

```python
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
```

This is computed from the file's own location
(`tests/backend/test_x.py` ΓåÆ `parents[2]` is the repo root ΓåÆ `/ "backend"`),
not from the current working directory. That was a deliberate choice over
having `run_tests.sh` `cd` into `backend/` before invoking each test:
Python sets `sys.path[0]` (where `import app...` gets resolved) from the
**script file's own directory**, not the process's working directory. A
`cd backend && python ../tests/backend/test_x.py` would still put
`tests/backend/` on `sys.path`, not `backend/` ΓÇö the `cd` wouldn't fix
anything. The per-file fixup works no matter how the file is invoked
(directly, through `run_tests.sh`, or collected by `pytest` from any
rootdir), which also matches every file's "written so pytest collects it
unchanged" docstring claim.

**When adding a new `tests/backend/test_*.py`**, copy that exact block in
before your first `app.`/`microservices.` import. That's the only
repo-specific ceremony; everything else is a normal standalone script.

`tests/frontend/demo.test.ts` has the equivalent problem for a different
reason: it moved out of `frontend/packages/core/lib/`, so its relative
imports of `demo.ts`, `content.ts`, `activity.ts`, and `apilog.ts` now point
back at `../../frontend/packages/core/lib/...` explicitly, since the source
those imports test still lives there and didn't move.

## 6. Writing a new test ΓÇö the house style

Match the existing files. Concretely:

1. **Module docstring** at the top: what it checks, the one-line run
   command, the "also written so pytest collects it unchanged" note, and a
   **Scope** paragraph naming exactly what's real vs. monkeypatched and why
   (network/DB/LLM calls are always faked; pure logic is always real).
2. **The `sys.path` fixup** (backend only), copied verbatim from any
   existing file ΓÇö see ┬º5.
3. **Small, explicit fixtures** built right next to the test that uses them
   ΓÇö hand-built dicts/objects, not shared setup/teardown machinery. There's
   no framework providing fixtures, and the existing files lean into that:
   a reader should be able to see the whole input and the whole expected
   output in one screen.
4. **One `test_*` function per behavior**, named as a full sentence
   (`test_reranker_failure_sets_none_not_a_backfilled_hybrid_score`, not
   `test_reranker_2`). The name is the only documentation a failure's
   traceback gives you at a glance, so make it carry the "what should be
   true" claim.
5. **Plain `assert`**, with a message where the failure wouldn't otherwise
   be self-explanatory (comparing two literal values usually doesn't need
   one; comparing derived/computed values usually does).
6. **A `__main__` block** that calls every `test_*` function in the module,
   prints `ok  <name>` after each, and prints `N checks passed` at the end.
   Copy this from the shortest existing file (`test_calendar_fallback.py` or
   `test_user_management.py`) rather than writing it from scratch.
7. **Monkeypatch by name on the module under test**, not on the module that
   defines the function ΓÇö see the note in ┬º4. Restore the original in a
   `finally` (or a small context-manager `_Patcher` class, as
   `test_agent4_conflicts.py` and others do) so one test's patch can't leak
   into the next.

**Before adding a check, search for it first** ΓÇö don't duplicate a case
that already exists under a different name:

```bash
grep -h "^def test_" tests/backend/test_*.py
```

**No new dependency, framework, or `requirements.txt`/`package.json` edit**
for the test suite itself, ever, without asking first ΓÇö the no-framework
convention is deliberate (see `CLAUDE.md` and this guide's intro), not
something to "improve" unilaterally.

## 7. Where this fits without CI

There's no pipeline that runs any of this automatically. `./run_tests.sh` is
the manual gate: run it (or at least `--unit`) before committing a change
that touches backend logic, auth, retrieval, the Greenlight Committee, the
calendar/Agent-4 integrations, or the shared frontend `lib/`. A change that
only touches one app's UI components can usually get away with just that
app's `npm run lint` / `npx tsc --noEmit` / `npm run build` ΓÇö `./run_tests.sh
--frontend` runs exactly those for both apps.

## 8. Quick reference

```bash
./run_tests.sh                                    # everything
./run_tests.sh --unit                              # fast: backend + demo.test.ts only
cd tests/backend && python test_auth.py            # one backend file
cd tests/frontend && node --experimental-strip-types demo.test.ts             # the frontend file
grep -h "^def test_" tests/backend/test_*.py       # check for an existing case before adding one
```
