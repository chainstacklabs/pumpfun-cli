#!/usr/bin/env bash
# check-prereqs.sh — Verify all prerequisites for e2e QA testing.
# Exit 0 if all critical checks pass, 1 if any fail.
set -uo pipefail

PASS=0
FAIL=0
WARN=0

pass() { echo "  PASS  $1"; ((PASS++)) || true; }
fail() { echo "  FAIL  $1"; ((FAIL++)) || true; }
warn() { echo "  WARN  $1"; ((WARN++)) || true; }

echo "=== pumpfun-cli E2E Prerequisites Check ==="
echo ""

# --- 1. PUMPFUN_RPC ---
if [[ -n "${PUMPFUN_RPC:-}" ]]; then
    pass "PUMPFUN_RPC is set (from environment)"
elif [[ -f .env ]] && grep -q '^PUMPFUN_RPC=' .env 2>/dev/null; then
    rpc_val="$(grep '^PUMPFUN_RPC=' .env | head -1 | cut -d= -f2-)"
    if [[ -n "$rpc_val" ]]; then
        export PUMPFUN_RPC="$rpc_val"
        pass "PUMPFUN_RPC loaded from .env"
    else
        fail "PUMPFUN_RPC is empty in .env"
    fi
else
    fail "PUMPFUN_RPC not set (checked env and .env file)"
fi

# --- 2. PUMPFUN_PASSWORD ---
if [[ -n "${PUMPFUN_PASSWORD:-}" ]]; then
    pass "PUMPFUN_PASSWORD is set"
else
    fail "PUMPFUN_PASSWORD not set — export it before running tests"
fi

# --- 3. Wallet exists ---
wallet_output=""
if wallet_output="$(uv run pumpfun wallet show 2>&1)"; then
    pubkey="$(echo "$wallet_output" | grep -oP '[A-HJ-NP-Za-km-z1-9]{32,44}' | head -1 || true)"
    if [[ -n "$pubkey" ]]; then
        pass "Wallet exists (pubkey: $pubkey)"
    else
        pass "Wallet exists (could not parse pubkey from output)"
    fi
else
    fail "Wallet not found — run 'uv run pumpfun wallet create' first"
    pubkey=""
fi

# --- 4. Balance >= 0.01 SOL ---
if [[ -n "$pubkey" ]]; then
    balance_output=""
    if balance_output="$(uv run pumpfun --json wallet balance 2>&1)"; then
        # Parse SOL balance from JSON output
        sol_balance="$(echo "$balance_output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # Handle both flat and nested formats
    if isinstance(data, dict):
        bal = data.get('sol', data.get('balance', data.get('sol_balance', 0)))
    else:
        bal = 0
    print(f'{float(bal):.6f}')
except Exception:
    print('0')
" 2>/dev/null || echo "0")"

        if [[ "$sol_balance" == "0" || "$sol_balance" == "0.000000" ]]; then
            fail "Could not parse balance from output"
        else
            # Compare using python for reliable float comparison
            sufficient="$(python3 -c "print('yes' if float('$sol_balance') >= 0.01 else 'no')" 2>/dev/null || echo "no")"
            if [[ "$sufficient" == "yes" ]]; then
                pass "Balance: ${sol_balance} SOL (>= 0.01 minimum)"
            else
                fail "Balance: ${sol_balance} SOL (need >= 0.01 SOL for trading tests)"
            fi
        fi
    else
        fail "Could not fetch wallet balance"
    fi
else
    fail "Skipping balance check — no wallet"
fi

# --- Summary ---
echo ""
echo "=== Summary: $PASS passed, $FAIL failed, $WARN warnings ==="

if [[ "$FAIL" -gt 0 ]]; then
    echo "Fix the failures above before running e2e tests."
    exit 1
else
    echo "All checks passed. Ready for e2e testing."
    exit 0
fi
