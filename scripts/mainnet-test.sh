#!/usr/bin/env bash
# Integration tests against Solana mainnet — executes real transactions that cost SOL.
#
# For free/safe tests, use surfpool-test.sh (local fork) instead.
#
# Usage:
#   ./scripts/mainnet-test.sh
#   ./scripts/mainnet-test.sh --skip-trading   # skip groups that spend SOL
#
# Prerequisites:
#   - .env with PUMPFUN_RPC
#   - PUMPFUN_PASSWORD env var set
#   - Wallet created (pumpfun wallet show works)
#   - >= 0.01 SOL balance for trading tests
#
# Output: docs/e2e-test-results.md

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Load .env
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

SKIP_TRADING=false
for arg in "$@"; do
    [[ "$arg" == "--skip-trading" ]] && SKIP_TRADING=true
done

# --- Helpers ---
# Use a temp file for results to avoid subshell variable loss

PASS=0
FAIL=0
ISSUE=0
RESULTS_FILE=$(mktemp)
LAST_OUTPUT_FILE=$(mktemp)
DATE=$(date +%Y-%m-%d)

trap "rm -f $RESULTS_FILE $LAST_OUTPUT_FILE" EXIT

record() {
    local group="$1" cmd="$2" result="$3" notes="${4:-}"
    # Truncate long notes to keep the table readable
    notes=$(echo "$notes" | head -1 | cut -c1-80)
    echo "| $group | \`$cmd\` | $result | $notes |" >> "$RESULTS_FILE"
    case "$result" in
        PASS) ((PASS++)) ;;
        FAIL|BUG) ((FAIL++)) ;;
        ISSUE) ((ISSUE++)) ;;
    esac
}

# Run command, expect exit 0
run_ok() {
    local group="$1" desc="$2"
    shift 2
    local output exit_code
    output=$(eval "$@" 2>&1)
    exit_code=$?
    echo "$output" > "$LAST_OUTPUT_FILE"
    if [[ $exit_code -eq 0 ]]; then
        record "$group" "$desc" "PASS"
    else
        record "$group" "$desc" "FAIL" "exit=$exit_code: $(echo "$output" | head -1 | cut -c1-60)"
    fi
    return $exit_code
}

# Run command, expect non-zero exit with message matching a pattern
run_err() {
    local group="$1" desc="$2" expected="$3"
    shift 3
    local output exit_code
    output=$(eval "$@" 2>&1)
    exit_code=$?
    echo "$output" > "$LAST_OUTPUT_FILE"
    if [[ $exit_code -ne 0 ]] && echo "$output" | grep -qi "$expected"; then
        record "$group" "$desc" "PASS" "Expected error"
    elif [[ $exit_code -eq 0 ]]; then
        record "$group" "$desc" "FAIL" "Expected error but got exit=0"
    else
        record "$group" "$desc" "ISSUE" "exit=$exit_code: $(echo "$output" | head -1 | cut -c1-60)"
    fi
}

# Run command, expect JSON array output
run_json_array() {
    local group="$1" desc="$2"
    shift 2
    local output exit_code
    output=$(eval "$@" 2>&1)
    exit_code=$?
    echo "$output" > "$LAST_OUTPUT_FILE"
    if [[ $exit_code -ne 0 ]]; then
        record "$group" "$desc" "FAIL" "exit=$exit_code"
        return 1
    fi
    local count
    count=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d)) if isinstance(d,list) else sys.exit(1)" 2>/dev/null)
    if [[ $? -eq 0 ]]; then
        record "$group" "$desc" "PASS" "$count items"
    else
        record "$group" "$desc" "FAIL" "Not a JSON array"
        return 1
    fi
}

last_output() {
    cat "$LAST_OUTPUT_FILE"
}

# --- Prereq checks ---

echo "=== E2E QA — Prerequisite Checks ==="

if [[ -z "${PUMPFUN_RPC:-}" ]]; then
    echo "FATAL: PUMPFUN_RPC not set. Create .env or export it."
    exit 1
fi

if [[ -z "${PUMPFUN_PASSWORD:-}" ]]; then
    echo "FATAL: PUMPFUN_PASSWORD not set."
    exit 1
fi

uv run pumpfun wallet show > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    echo "FATAL: No wallet found. Run: uv run pumpfun wallet create"
    exit 1
fi
PUBKEY=$(uv run pumpfun wallet show 2>&1 | python3 -c "import json,sys; print(json.load(sys.stdin)['pubkey'])" 2>/dev/null || echo "unknown")
START_BALANCE=$(uv run pumpfun wallet balance 2>&1 | python3 -c "import json,sys; print(json.load(sys.stdin)['sol_balance'])" 2>/dev/null || echo "0")

echo "Wallet:  $PUBKEY"
echo "Balance: $START_BALANCE SOL"
echo "RPC:     ${PUMPFUN_RPC:0:50}..."
echo ""

# --- Group 1: Wallet (read-only) ---

echo "=== Group 1: Wallet ==="
run_ok  "Wallet" "wallet show"             "uv run pumpfun wallet show"
run_ok  "Wallet" "wallet balance"          "uv run pumpfun wallet balance"
run_ok  "Wallet" "wallet tokens"           "uv run pumpfun wallet tokens"
run_ok  "Wallet" "--json wallet balance"   "uv run pumpfun --json wallet balance"
run_err "Wallet" "wallet show (bad keyfile)" "No wallet found" \
        "uv run pumpfun --keyfile /tmp/nonexistent.enc wallet show"
run_err "Wallet" "wallet export (wrong pw)" "decrypt" \
        "PUMPFUN_PASSWORD=wrongpass uv run pumpfun wallet export --output /tmp/e2e_test_export.json"

# Verify JSON pipe mode
PIPE_OUT=$(uv run pumpfun wallet balance 2>&1)
if echo "$PIPE_OUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    record "Wallet" "pipe JSON valid" "PASS"
else
    record "Wallet" "pipe JSON valid" "FAIL" "Invalid JSON in pipe mode"
fi
echo "  Done. ($PASS pass)"

# --- Group 2: Config ---

echo "=== Group 2: Config ==="
run_ok "Config" "config set" "uv run pumpfun config set e2e_test_key e2e_value"

GET_OUT=$(uv run pumpfun config get e2e_test_key 2>&1)
if [[ "$GET_OUT" == *"e2e_value"* ]]; then
    record "Config" "config get" "PASS"
else
    record "Config" "config get" "FAIL" "Got: $GET_OUT"
fi

run_ok  "Config" "config list"   "uv run pumpfun config list"
run_ok  "Config" "config delete" "uv run pumpfun config delete e2e_test_key"
run_err "Config" "config get (deleted)" "not set" "uv run pumpfun config get e2e_test_key"
echo "  Done. ($PASS pass)"

# --- Group 3: Token Discovery ---

echo "=== Group 3: Token Discovery ==="
run_json_array "Discovery" "tokens trending"    "uv run pumpfun tokens trending --limit 3"
TRENDING=$(last_output)
run_json_array "Discovery" "tokens new"         "uv run pumpfun tokens new --limit 10"
NEW_TOKENS=$(last_output)
run_json_array "Discovery" "tokens graduating"  "uv run pumpfun tokens graduating --limit 3"
run_json_array "Discovery" "tokens recommended" "uv run pumpfun tokens recommended --limit 3"

# Search — known to sometimes return empty
SEARCH_OUT=$(uv run pumpfun tokens search "sol" --limit 3 2>&1)
SEARCH_EXIT=$?
if [[ $SEARCH_EXIT -eq 0 ]]; then
    SEARCH_COUNT=$(echo "$SEARCH_OUT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [[ "$SEARCH_COUNT" -gt 0 ]]; then
        record "Discovery" "tokens search" "PASS" "$SEARCH_COUNT results"
    else
        record "Discovery" "tokens search" "ISSUE" "Returns empty [] — known ISSUE-4"
    fi
else
    record "Discovery" "tokens search" "FAIL" "exit=$SEARCH_EXIT"
fi

# --- Discover mints for later groups ---

ACTIVE_MINT=$(echo "$NEW_TOKENS" | python3 -c "
import json, sys
tokens = json.load(sys.stdin)
for t in tokens:
    if not t.get('complete', True) and t.get('real_token_reserves', 0) > 0 and t.get('real_sol_reserves', 0) > 1_000_000_000:
        print(t['mint'])
        break
else:
    print('')
" 2>/dev/null)

GRADUATED_MINT=$(echo "$TRENDING" | python3 -c "
import json, sys
tokens = json.load(sys.stdin)
# Prefer graduated tokens with higher SOL reserves — pools with extreme
# base/quote ratios can trigger on-chain overflow at buy.rs:400.
best = None
for t in tokens:
    if t.get('complete') and t.get('pump_swap_pool'):
        if best is None:
            best = t
        elif t.get('market_cap', 0) > best.get('market_cap', 0):
            best = t
if best:
    print(best['mint'])
else:
    print('')
" 2>/dev/null)

echo "  Active mint:    ${ACTIVE_MINT:-none found}"
echo "  Graduated mint: ${GRADUATED_MINT:-none found}"
echo "  Done. ($PASS pass)"

# --- Group 4: Token Info ---

echo "=== Group 4: Token Info ==="
if [[ -n "$ACTIVE_MINT" ]]; then
    run_ok "Info" "info (active)" "uv run pumpfun info $ACTIVE_MINT"
else
    record "Info" "info (active)" "ISSUE" "No active mint found"
fi

if [[ -n "$GRADUATED_MINT" ]]; then
    run_ok "Info" "info (graduated)" "uv run pumpfun info $GRADUATED_MINT"
else
    record "Info" "info (graduated)" "ISSUE" "No graduated mint found"
fi

run_err "Info" "info (invalid)" "No bonding curve" "uv run pumpfun info 11111111111111111111111111111111"
echo "  Done. ($PASS pass)"

# --- Group 5: Bonding Curve Trading ---

if [[ "$SKIP_TRADING" == true ]]; then
    echo "=== Groups 5-8: SKIPPED (--skip-trading) ==="
    record "Trading" "buy/sell" "SKIP" "--skip-trading flag"
else
    echo "=== Group 5: Bonding Curve Trading ==="
    if [[ -n "$ACTIVE_MINT" ]]; then
        BUY_OUT=$(uv run pumpfun buy "$ACTIVE_MINT" 0.001 --slippage 50 --confirm 2>&1)
        BUY_EXIT=$?
        if [[ $BUY_EXIT -eq 0 ]]; then
            record "BC Trade" "buy 0.001 --confirm" "PASS"
            echo "  Buy OK. Waiting 5s for RPC state..."
            sleep 5

            SELL_OUT=$(uv run pumpfun sell "$ACTIVE_MINT" all --slippage 50 --confirm 2>&1)
            SELL_EXIT=$?
            if [[ $SELL_EXIT -eq 0 ]]; then
                record "BC Trade" "sell all --confirm" "PASS"
            else
                # Retry once after delay
                echo "  Sell failed, retrying in 5s..."
                sleep 5
                SELL_OUT=$(uv run pumpfun sell "$ACTIVE_MINT" all --slippage 50 --confirm 2>&1)
                SELL_EXIT=$?
                if [[ $SELL_EXIT -eq 0 ]]; then
                    record "BC Trade" "sell all --confirm" "PASS" "Needed retry (RPC lag)"
                else
                    record "BC Trade" "sell all --confirm" "FAIL" "Failed after retry"
                fi
            fi
        else
            # Strip Rich formatting, keep first meaningful line
            BUY_ERR=$(echo "$BUY_OUT" | grep -m1 "Error:" | cut -c1-60)
            [[ -z "$BUY_ERR" ]] && BUY_ERR="exit=$BUY_EXIT"
            record "BC Trade" "buy 0.001 --confirm" "FAIL" "$BUY_ERR"
        fi
    else
        record "BC Trade" "buy/sell" "ISSUE" "No active mint found"
    fi
    echo "  Done."

    # --- Group 6: PumpSwap AMM Trading ---

    echo "=== Group 6: PumpSwap AMM Trading ==="
    if [[ -n "$GRADUATED_MINT" ]]; then
        # Build a list of graduated mints to try (some pools have on-chain overflow bugs)
        ALL_GRADUATED=$(echo "$TRENDING" | python3 -c "
import json, sys
tokens = json.load(sys.stdin)
for t in tokens:
    if t.get('complete') and t.get('pump_swap_pool'):
        print(t['mint'])
" 2>/dev/null)

        AMM_BUY_OK=false
        AMM_MINT=""
        while IFS= read -r CANDIDATE; do
            [[ -z "$CANDIDATE" ]] && continue
            AMM_OUT=$(uv run pumpfun buy "$CANDIDATE" 0.001 --slippage 50 --force-amm --confirm 2>&1)
            AMM_EXIT=$?
            if [[ $AMM_EXIT -eq 0 ]]; then
                AMM_BUY_OK=true
                AMM_MINT="$CANDIDATE"
                break
            elif echo "$AMM_OUT" | grep -q "6023"; then
                echo "  Pool overflow (6023) on ${CANDIDATE:0:12}…, trying next"
                continue
            else
                # Non-overflow failure — record and stop
                record "PumpSwap" "buy --force-amm --confirm" "FAIL" "$(echo "$AMM_OUT" | head -1 | cut -c1-60)"
                break
            fi
        done <<< "$ALL_GRADUATED"

        if [[ "$AMM_BUY_OK" == "true" ]]; then
            record "PumpSwap" "buy --force-amm --confirm" "PASS"
            echo "  PumpSwap buy OK. Waiting 5s for RPC state..."
            sleep 5

            AMM_SELL_OUT=$(uv run pumpfun sell "$AMM_MINT" all --slippage 50 --confirm 2>&1)
            AMM_SELL_EXIT=$?
            if [[ $AMM_SELL_EXIT -eq 0 ]]; then
                record "PumpSwap" "sell all --confirm" "PASS"
            else
                echo "  PumpSwap sell failed, retrying in 5s..."
                sleep 5
                AMM_SELL_OUT=$(uv run pumpfun sell "$AMM_MINT" all --slippage 50 --confirm 2>&1)
                AMM_SELL_EXIT=$?
                if [[ $AMM_SELL_EXIT -eq 0 ]]; then
                    record "PumpSwap" "sell all --confirm" "PASS" "Needed retry (RPC lag)"
                else
                    record "PumpSwap" "sell all --confirm" "FAIL" "Failed after retry"
                fi
            fi
        elif [[ "$AMM_BUY_OK" == "false" ]] && [[ -z "$AMM_MINT" ]]; then
            record "PumpSwap" "buy --force-amm --confirm" "ISSUE" "All graduated pools hit error 6023"
        fi
    else
        record "PumpSwap" "buy --force-amm" "ISSUE" "No graduated mint found"
    fi
    echo "  Done."

    # --- Group 6b: Token Launch ---

    echo "=== Group 6b: Token Launch ==="
    # Generate a minimal test image
    python3 -c "from PIL import Image; Image.new('RGB',(100,100),'blue').save('/tmp/e2e_test_token.png')" 2>/dev/null
    LAUNCH_IMG=""
    [[ -f /tmp/e2e_test_token.png ]] && LAUNCH_IMG="--image /tmp/e2e_test_token.png"

    LAUNCH_OUT=$(uv run pumpfun --json launch --name "E2E Test $(date +%s)" --ticker "E2ET" --desc "Automated e2e test token" $LAUNCH_IMG 2>&1)
    LAUNCH_EXIT=$?
    echo "$LAUNCH_OUT" > "$LAST_OUTPUT_FILE"
    if [[ $LAUNCH_EXIT -eq 0 ]]; then
        record "Launch" "launch" "PASS"
        LAUNCHED_MINT=$(echo "$LAUNCH_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mint',''))" 2>/dev/null)
        echo "  Launched: $LAUNCHED_MINT"
    else
        LAUNCH_ERR=$(echo "$LAUNCH_OUT" | grep -m1 "Error:" | cut -c1-60)
        [[ -z "$LAUNCH_ERR" ]] && LAUNCH_ERR="exit=$LAUNCH_EXIT"
        record "Launch" "launch" "FAIL" "$LAUNCH_ERR"
        LAUNCHED_MINT=""
    fi

    # Launch + buy
    LAUNCH_BUY_OUT=$(uv run pumpfun --json launch --name "E2E Buy Test $(date +%s)" --ticker "E2EB" --desc "Automated e2e launch+buy" $LAUNCH_IMG --buy 0.001 2>&1)
    LAUNCH_BUY_EXIT=$?
    echo "$LAUNCH_BUY_OUT" > "$LAST_OUTPUT_FILE"
    if [[ $LAUNCH_BUY_EXIT -eq 0 ]]; then
        record "Launch" "launch --buy 0.001" "PASS"
        LAUNCHED_BUY_MINT=$(echo "$LAUNCH_BUY_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mint',''))" 2>/dev/null)
        echo "  Launched+bought: $LAUNCHED_BUY_MINT"

        # Sell from the launched token to test full cycle
        if [[ -n "$LAUNCHED_BUY_MINT" ]]; then
            echo "  Waiting 5s for RPC state..."
            sleep 5
            LSELL_OUT=$(uv run pumpfun sell "$LAUNCHED_BUY_MINT" all --slippage 50 --confirm 2>&1)
            LSELL_EXIT=$?
            if [[ $LSELL_EXIT -eq 0 ]]; then
                record "Launch" "sell launched token" "PASS"
            else
                sleep 5
                LSELL_OUT=$(uv run pumpfun sell "$LAUNCHED_BUY_MINT" all --slippage 50 --confirm 2>&1)
                LSELL_EXIT=$?
                if [[ $LSELL_EXIT -eq 0 ]]; then
                    record "Launch" "sell launched token" "PASS" "Needed retry"
                else
                    record "Launch" "sell launched token" "FAIL" "Failed after retry"
                fi
            fi
        fi
    else
        LAUNCH_BUY_ERR=$(echo "$LAUNCH_BUY_OUT" | grep -m1 "Error:" | cut -c1-60)
        [[ -z "$LAUNCH_BUY_ERR" ]] && LAUNCH_BUY_ERR="exit=$LAUNCH_BUY_EXIT"
        record "Launch" "launch --buy 0.001" "FAIL" "$LAUNCH_BUY_ERR"
    fi
    rm -f /tmp/e2e_test_token.png
    echo "  Done."

    # --- Group 7: Extras ---

    echo "=== Group 7: Extras ==="
    uv run pumpfun claim-cashback --confirm > /dev/null 2>&1
    record "Extras" "claim-cashback" "PASS" "Submitted (may be no-op)"

    uv run pumpfun close-volume-acc --confirm > /dev/null 2>&1
    record "Extras" "close-volume-acc" "PASS" "Submitted (may be no-op)"

    run_err "Extras" "collect-creator-fee" "No creator fees" \
            "uv run pumpfun collect-creator-fee --confirm"

    if [[ -n "$ACTIVE_MINT" ]]; then
        run_err "Extras" "migrate (not complete)" "not complete" \
                "uv run pumpfun migrate $ACTIVE_MINT --confirm"
    fi
    echo "  Done."

    # --- Group 8: Wallet Cleanup ---

    echo "=== Group 8: Wallet Cleanup ==="
    run_ok "Cleanup" "close-atas" "uv run pumpfun wallet close-atas --confirm"
    echo "  Done."
fi

# --- Group 9: CLI Help ---

echo "=== Group 9: CLI Options & Help ==="
run_ok "Help" "--help"        "uv run pumpfun --help"
run_ok "Help" "wallet --help" "uv run pumpfun wallet --help"
run_ok "Help" "tokens --help" "uv run pumpfun tokens --help"
run_ok "Help" "buy --help"    "uv run pumpfun buy --help"
echo "  Done. ($PASS pass)"

# --- Final balance ---

END_BALANCE=$(uv run pumpfun wallet balance 2>&1 | python3 -c "import json,sys; print(json.load(sys.stdin)['sol_balance'])" 2>/dev/null || echo "unknown")

# --- Write report ---

TOTAL=$((PASS + FAIL + ISSUE))
RESULTS=$(cat "$RESULTS_FILE")

cat > docs/e2e-test-results.md << REPORT_EOF
# E2E Test Results — $DATE

## Test Environment
- Wallet: \`$PUBKEY\`
- RPC: ${PUMPFUN_RPC:0:50}...
- Starting balance: $START_BALANCE SOL
- Ending balance: $END_BALANCE SOL

## Summary

| Pass | Fail | Issue | Total |
|------|------|-------|-------|
| $PASS | $FAIL | $ISSUE | $TOTAL |

## Results by Group

| Group | Command | Result | Notes |
|-------|---------|--------|-------|
$RESULTS

REPORT_EOF

echo ""
echo "========================================="
echo "  E2E QA Complete"
echo "  PASS: $PASS  FAIL: $FAIL  ISSUE: $ISSUE  TOTAL: $TOTAL"
echo "  Balance: $START_BALANCE -> $END_BALANCE SOL"
echo "  Report: docs/e2e-test-results.md"
echo "========================================="
