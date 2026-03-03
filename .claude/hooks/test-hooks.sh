#!/usr/bin/env bash
# Functional tests for Claude Code hooks.
# Run from project root: ./.claude/hooks/test-hooks.sh

set -euo pipefail

PROJ="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0
FAIL=0

run_test() {
    local name="$1" hook="$2" input="$3" expect_exit="$4" expect_stderr="$5"

    actual_stderr=$(echo "$input" | CLAUDE_PROJECT_DIR="$PROJ" uv run python "$PROJ/.claude/hooks/$hook" 2>&1 1>/dev/null || true)
    actual_exit=$(echo "$input" | CLAUDE_PROJECT_DIR="$PROJ" uv run python "$PROJ/.claude/hooks/$hook" >/dev/null 2>/dev/null; echo $?)

    local ok=true

    if [[ "$actual_exit" != "$expect_exit" ]]; then
        echo "FAIL: $name — expected exit $expect_exit, got $actual_exit"
        ok=false
    fi

    if [[ -n "$expect_stderr" && "$actual_stderr" != *"$expect_stderr"* ]]; then
        echo "FAIL: $name — stderr missing '$expect_stderr'"
        echo "  got: $actual_stderr"
        ok=false
    fi

    if [[ -z "$expect_stderr" && -n "$actual_stderr" ]]; then
        echo "FAIL: $name — expected no stderr, got: $actual_stderr"
        ok=false
    fi

    if $ok; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
}

echo "=== guard.py (PreToolUse Write|Edit) ==="

run_test "blocks .env" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/.env"}}' \
    "2" "BLOCKED: .env is a secrets file"

run_test "blocks .env.production" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/.env.production"}}' \
    "2" "BLOCKED: .env.production is a secrets file"

run_test "blocks idl/ files" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/idl/pump_fun_idl.json"}}' \
    "2" "source-of-truth from on-chain"

run_test "blocks wallet.enc" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/some/path/wallet.enc"}}' \
    "2" "encrypted wallet keystore"

run_test "blocks .pem files" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/certs/server.pem"}}' \
    "2" "credential file"

run_test "blocks .key files" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/certs/private.key"}}' \
    "2" "credential file"

run_test "allows normal Python files" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/src/pumpfun_cli/cli.py"}}' \
    "0" ""

run_test "allows .env.example" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/.env.example"}}' \
    "0" ""

run_test "allows README.md" "guard.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/README.md"}}' \
    "0" ""

echo ""
echo "=== bash-guard.py (PreToolUse Bash) — advisory only ==="

run_test "warns on pumpfun buy (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"uv run pumpfun buy ABC123 0.1"}}' \
    "0" "sends a Solana transaction"

run_test "warns on pumpfun sell (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"pumpfun sell ABC123 100%"}}' \
    "0" "sends a Solana transaction"

run_test "warns on pumpfun transfer (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"uv run pumpfun transfer 1.0 dest"}}' \
    "0" "sends a Solana transaction"

run_test "warns on pumpfun launch (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"pumpfun launch --name TEST"}}' \
    "0" "sends a Solana transaction"

run_test "warns on pumpfun migrate (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"uv run pumpfun migrate ABC123"}}' \
    "0" "sends a Solana transaction"

run_test "warns on mainnet-test.sh (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"./scripts/mainnet-test.sh"}}' \
    "0" "mainnet end-to-end tests"

run_test "warns on rm .env (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"rm .env"}}' \
    "0" "deletes a sensitive file"

run_test "warns on rm wallet.enc (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"rm -f ~/.config/pumpfun-cli/wallet.enc"}}' \
    "0" "deletes a sensitive file"

run_test "warns on rm -rf idl/ (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"rm -rf idl/"}}' \
    "0" "deletes IDL files"

run_test "silent on pytest (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"uv run pytest tests/ -q"}}' \
    "0" ""

run_test "silent on git status (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"git status"}}' \
    "0" ""

run_test "silent on uv sync (exit 0)" "bash-guard.py" \
    '{"tool_input":{"command":"uv sync --dev"}}' \
    "0" ""

echo ""
echo "=== lint.py (PostToolUse Write|Edit) ==="

run_test "runs on Python files (exit 0)" "lint.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/src/pumpfun_cli/cli.py"}}' \
    "0" ""

run_test "skips non-Python files (exit 0)" "lint.py" \
    '{"tool_input":{"file_path":"'"$PROJ"'/README.md"}}' \
    "0" ""

run_test "skips files outside project (exit 0)" "lint.py" \
    '{"tool_input":{"file_path":"/tmp/random.py"}}' \
    "0" ""

echo ""
echo "================================"
echo "PASS: $PASS  FAIL: $FAIL"
if [[ $FAIL -gt 0 ]]; then
    echo "SOME TESTS FAILED"
    exit 1
else
    echo "ALL TESTS PASSED"
fi
