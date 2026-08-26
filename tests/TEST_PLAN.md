# Test plan

Risk-prioritized plain-assert test suite for Agentic Studio. No test
framework (no pytest, no vitest) ΓÇö every file runs standalone with a bare
interpreter, matching the convention already established by the first three
backend tests and `demo.test.ts` (see `CLAUDE.md`). Every file is also
structured so `pytest` would collect it unchanged if that's ever added, but
nothing in this repo requires it.

All test-related files live under this directory: `tests/backend/` and
`tests/frontend/`. Nothing test-related is left inside `backend/` or
`frontend/` themselves.

## Why these areas

Prioritized by "what breaks silently and how bad is it," per CLAUDE.md's own
descriptions of the riskiest corners of the codebase:

| Risk area | File(s) | Why it's risky |
|---|---|---|
| Release-date conflict logic + retrieval confidence gate | `test_release_conflicts.py` | Pure date arithmetic that replaced an LLM call specifically because the LLM could hallucinate a film ΓÇö a regression here reintroduces silent wrong answers. `retrieval_status()`'s four states are easy to collapse back into a boolean by accident. |
| Admin table browser SQL-identifier safety | `test_admin_tables.py` | The one place in the codebase that builds SQL from names instead of only values. A regex bypass here is a SQL injection path. |
| Login sessions / role gate | `test_auth.py` | Password hashing, JWT roundtrip/tamper, and `require_role`'s re-check-on-every-call (not just the JWT claim) ΓÇö the mechanism that stops a demoted or deleted account from keeping developer access for up to 12h. |
| Last-developer lockout guard | `test_user_management.py` | `_refuse_if_last_developer` is the only thing stopping every `/admin/*` and `/auth/users` route from being locked out with no way back short of direct DB access. |
| Hybrid retrieval pipeline (dense+BM25 blend, reranker failure) | `test_retrieval_pipeline.py` | Pins down the exact bug class described in CLAUDE.md: back-filling `rerank_score` (0-10) from `hybrid_score` (0.0-1.0) makes every reranker outage look identical to "no relevant guidelines found." |
| Greenlight Committee debate graph | `test_greenlight_committee.py` | The one task (`greenlight`) that isn't a single routed node ΓÇö a whole separate multi-node LangGraph with its own stalemate/iteration-cap logic and RED/YELLOW/GREEN verdict rules. |
| Release-date state-carrier string | `test_release_date_state_carrier.py` | Four endpoints (`/check-conflicts`, `/confirm-date`, `/override-date`, `/finalize-calendar`) all re-split the same `"<date>|<listing_result_id>"` string; changing the format silently breaks all four. Also exercises `_nearest_clear_date`'s known one-shot-shift limitation directly. |
| Calendar MCP ΓåÆ service-account silent fallback | `test_calendar_fallback.py` | `CALENDAR_MODE=mcp` failures are swallowed and silently retried on the service-account path ΓÇö worth pinning down that failures of the *fallback itself* are not also swallowed. |
| Agent 4 date-conflict logic | `test_agent4_conflicts.py` | Holiday lookups (external API, monkeypatched) plus the hardcoded 2026-2028 sporting/awards windows CLAUDE.md flags as a silent-rot risk. |
| Rate limiter / retry / safe-generate fallback | `test_resilience.py` | Shared in-process state used by `/run-agent`, `/check-conflicts`, `/finalize-calendar`, and `/auth/login` ΓÇö a bug here is a bug on all of them simultaneously. |
| Query-safety gate | `test_guardrails.py` | The only thing standing between a raw form field and the supervisor on the `/run-agent` path. |
| Demo Mode, walkthroughs, activity narration, API-key masking | `tests/frontend/demo.test.ts` | Demo Mode's contract is "every endpoint has a fixture, or it throws" ΓÇö an easy thing to silently violate when adding an endpoint. |

## Coverage vs. scope

Original scope for this suite: backend logic, auth/role-gate, RAG confidence
gate, Greenlight Committee, external integration failure modes, frontend
checks. All six are covered by the table above ΓÇö no gap was found when this
plan was last reconciled against the filesystem (2026-08-22).

## Layout

```
tests/
  TEST_PLAN.md              this file
  backend/
    test_admin_tables.py            17 checks
    test_agent4_conflicts.py         9 checks
    test_auth.py                    11 checks
    test_calendar_fallback.py        4 checks
    test_greenlight_committee.py    14 checks
    test_guardrails.py              15 checks
    test_release_conflicts.py       15 checks
    test_release_date_state_carrier.py  7 checks
    test_resilience.py              12 checks
    test_retrieval_pipeline.py       8 checks
    test_user_management.py          5 checks
  frontend/
    demo.test.ts               Demo Mode, walkthroughs, activity, API log
```

## Working-directory / import fix

Per `CLAUDE.md`, every backend module imports via the `app.` package prefix,
which only resolves with `backend/` on `sys.path`. Since these test files no
longer live inside `backend/`, each `tests/backend/test_*.py` inserts
`backend/`'s absolute path onto `sys.path` at the top of the file, computed
from its own `__file__` (`Path(__file__).resolve().parents[2] / "backend"`):

```python
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
```

This was chosen over having the runner `cd` into `backend/` before invoking
each test, because Python's `sys.path[0]` is set from the *script's own*
directory, not the process's working directory ΓÇö a `cd backend && python
../tests/backend/test_foo.py` would still leave `tests/backend/` (not
`backend/`) as `sys.path[0]`, so the `app.` imports would fail regardless of
cwd. The per-file fixup works no matter how the file is invoked (directly,
via `run_tests.sh`, or via `pytest` from any rootdir), which also matches
every file's existing "written so pytest collects it unchanged" claim.

`tests/frontend/demo.test.ts` uses the equivalent fix for relative imports:
since it moved out of `frontend/packages/core/lib/`, its imports of
`demo.ts`, `content.ts`, `activity.ts`, and `apilog.ts` now point back at
`../../frontend/packages/core/lib/...` explicitly.

## Running

```bash
./run_tests.sh              # everything: backend + frontend unit + lint/tsc/build
./run_tests.sh --backend    # tests/backend/test_*.py only
./run_tests.sh --frontend   # demo.test.ts + lint/tsc/build for both apps
./run_tests.sh --unit       # backend + demo.test.ts, skip lint/tsc/build
```

Or run a single file directly:

```bash
cd tests/backend && ../../venv/Scripts/python.exe test_auth.py   # Windows venv
cd tests/backend && python test_auth.py                          # any Python with deps installed
cd tests/frontend && node --experimental-strip-types demo.test.ts
```

## Adding a new test file

- Backend: drop a `tests/backend/test_*.py`, plain asserts, no framework,
  runnable standalone. Copy the `sys.path` fixup block above verbatim before
  any `app.`/`microservices.` import. `run_tests.sh` picks up any
  `tests/backend/test_*.py` automatically ΓÇö no edit to the script needed.
- Frontend: extend `tests/frontend/demo.test.ts` (or add a sibling
  `tests/frontend/*.test.ts` and wire it into `run_tests.sh`'s
  `run_frontend_unit` step ΓÇö there's only one file today, so the step is
  hardcoded to it).
- Before adding a new check, grep the existing files for the behavior first
  (`grep -h "^def test_" tests/backend/test_*.py`) ΓÇö don't duplicate a case
  that already exists under a different name.

## Known stale doc references

`CLAUDE.md` and `PROJECT_GUIDE.md` still describe the pre-move layout in a
few places (`backend/test_*.py`, `frontend/packages/core/lib/demo.test.ts`
as the run location). This plan and `run_tests.sh` are authoritative on the
current location; those two docs were intentionally left unedited pending
a decision on updating `CLAUDE.md` itself (project convention doc, not
in this task's stated scope) ΓÇö see the migration notes for this move.
