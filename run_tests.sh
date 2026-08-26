#!/usr/bin/env bash
# Runs every check in the repo (tests/backend/test_*.py, tests/frontend/demo.test.ts,
# and frontend lint/typecheck) in sequence, prints a pass/fail summary, and
# exits non-zero on any failure. There is no CI pipeline, so
# this doubles as the manual gate to run before committing a change.
#
# All test-related files live under tests/ (tests/backend/, tests/frontend/;
# see tests/TEST_PLAN.md), not inside backend/ or frontend/ themselves.
# Backend test files import backend modules via the `app.` package prefix
# (per CLAUDE.md, that only resolves with backend/ on sys.path); rather than
# rely on this script's cwd for that, each tests/backend/test_*.py inserts
# backend/ onto sys.path itself at import time (relative to its own __file__),
# so it works the same way whether invoked from here, directly, or via pytest.
#
# Usage:
#   ./run_tests.sh              # everything
#   ./run_tests.sh --backend    # tests/backend/test_*.py only
#   ./run_tests.sh --frontend   # demo.test.ts + lint/tsc/build for both apps
#   ./run_tests.sh --unit       # tests/backend/test_*.py + demo.test.ts, skip lint/tsc/build
#
# Adding a new test file later: drop a tests/backend/test_*.py (plain asserts,
# runnable standalone, sys.path fixup at top per the existing files) or extend
# tests/frontend/demo.test.ts ΓÇö both are picked up automatically, no edit to
# this script required.

set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(pwd)"

MODE="${1:-all}"

PYTHON="$REPO_ROOT/venv/Scripts/python.exe"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$REPO_ROOT/venv/bin/python"
fi
if [ ! -x "$PYTHON" ]; then
  PYTHON="python"
fi

PASS=0
FAIL=0
FAILED_NAMES=()

run_step() {
  local name="$1"
  shift
  echo ""
  echo "=== $name ==="
  if "$@"; then
    PASS=$((PASS + 1))
    echo "--- PASS: $name ---"
  else
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
    echo "--- FAIL: $name ---"
  fi
}

run_backend() {
  echo ""
  echo "############################"
  echo "# Backend (plain asserts)  #"
  echo "############################"
  pushd tests/backend > /dev/null || return 1
  for f in test_*.py; do
    [ -e "$f" ] || continue
    run_step "tests/backend/$f" "$PYTHON" "$f"
  done
  popd > /dev/null
}

run_frontend_unit() {
  echo ""
  echo "################################"
  echo "# Frontend unit (demo.test.ts) #"
  echo "################################"
  pushd tests/frontend > /dev/null || return 1
  run_step "tests/frontend/demo.test.ts" node --experimental-strip-types demo.test.ts
  popd > /dev/null
}

run_frontend_app_checks() {
  echo ""
  echo "################################"
  echo "# Frontend (unified Next.js app)"
  echo "################################"
  pushd "frontend" > /dev/null || return 1
  run_step "frontend: npm run lint" npm run lint
  run_step "frontend: tsc --noEmit" npx tsc --noEmit
  popd > /dev/null
}

case "$MODE" in
  --backend)
    run_backend
    ;;
  --frontend)
    run_frontend_unit
    run_frontend_app_checks
    ;;
  --unit)
    run_backend
    run_frontend_unit
    ;;
  all|"")
    run_backend
    run_frontend_unit
    run_frontend_app_checks
    ;;
  *)
    echo "Unknown mode: $MODE (expected --backend, --frontend, --unit, or no argument)"
    exit 2
    ;;
esac

echo ""
echo "============================"
echo " SUMMARY: $PASS passed, $FAIL failed"
echo "============================"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed:"
  for n in "${FAILED_NAMES[@]}"; do
    echo "  - $n"
  done
  exit 1
fi
exit 0
