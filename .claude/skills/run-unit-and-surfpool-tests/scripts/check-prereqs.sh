#!/usr/bin/env bash
# Check prerequisites for running pumpfun-cli tests.
# Exit 0 if unit tests can run, 1 if not.
# Surfpool missing is a WARN (unit tests still work).

set -uo pipefail

passed=0
warned=0
failed=0

pass() { echo "  PASS  $1"; ((passed++)) || true; }
warn() { echo "  WARN  $1"; ((warned++)) || true; }
fail() { echo "  FAIL  $1"; ((failed++)) || true; }

# 1. uv installed
if command -v uv &>/dev/null; then
  pass "uv is installed ($(uv --version 2>/dev/null || echo 'unknown version'))"
else
  fail "uv is not installed — install from https://docs.astral.sh/uv/"
fi

# 2. pytest available via uv
if uv run pytest --version &>/dev/null; then
  pass "pytest is available ($(uv run pytest --version 2>/dev/null | head -1))"
else
  fail "pytest not available — run 'uv sync' to install dependencies"
fi

# 3. surfpool installed (optional)
if command -v surfpool &>/dev/null; then
  pass "surfpool is installed ($(surfpool --version 2>/dev/null || echo 'unknown version'))"
else
  warn "surfpool is not installed — integration tests will not run (unit tests are fine)"
fi

echo ""
echo "Summary: $passed passed, $warned warnings, $failed failed"

if [ "$failed" -gt 0 ]; then
  echo "Cannot run tests — fix FAIL items above."
  exit 1
else
  echo "Ready to run unit tests."
  exit 0
fi
