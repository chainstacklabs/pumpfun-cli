#!/usr/bin/env bash
# Core surfpool test runner — starts a local Solana fork and runs pytest against it.
#
# This is the script that actually starts surfpool and runs the tests.
# You must provide mint addresses via --mint / --graduated flags.
#
# If you don't have mints handy, use surfpool-autodiscover.sh instead —
# it queries the pump.fun API to find suitable tokens and calls this script.
#
# Usage:
#   ./scripts/surfpool-test.sh --mint <MINT> --graduated <GRAD_MINT>
#   ./scripts/surfpool-test.sh --running --mint <MINT>  # surfpool already running
#
# Prerequisites:
#   - surfpool installed: curl -sL https://run.surfpool.run/ | bash
#   - project installed:  uv sync --group dev

set -euo pipefail

SURFPOOL_RPC="${SURFPOOL_RPC:-http://127.0.0.1:8899}"
SURFPOOL_PORT="${SURFPOOL_RPC##*:}"  # extract port from URL
SURFPOOL_MANAGED=true
MINT=""
GRADUATED_MINT=""
EXTRA_ARGS=()
SURFPOOL_LOG=$(mktemp /tmp/surfpool-XXXX.log)

while [[ $# -gt 0 ]]; do
    case $1 in
        --mint)        MINT="$2"; shift 2 ;;
        --graduated)   GRADUATED_MINT="$2"; shift 2 ;;
        --running)     SURFPOOL_MANAGED=false; shift ;;
        --rpc)         SURFPOOL_RPC="$2"; shift 2 ;;
        *)             EXTRA_ARGS+=("$1"); shift ;;
    esac
done

cleanup() {
    if [[ "$SURFPOOL_MANAGED" == true ]] && [[ -n "${SURFPOOL_PID:-}" ]]; then
        echo "Stopping surfpool (pid $SURFPOOL_PID)..."
        kill "$SURFPOOL_PID" 2>/dev/null || true
        wait "$SURFPOOL_PID" 2>/dev/null || true
        # Wait for port to be fully released
        for _ in $(seq 1 20); do
            lsof -iTCP:"$SURFPOOL_PORT" -sTCP:LISTEN -t &>/dev/null || break
            sleep 0.5
        done
    fi
    rm -f "$SURFPOOL_LOG"
}
trap cleanup EXIT

# Generate a test keypair and get its pubkey
KEYPAIR_JSON=$(uv run python3 -c "
from solders.keypair import Keypair
kp = Keypair()
print(str(kp.pubkey()))
")
TEST_PUBKEY="$KEYPAIR_JSON"

if [[ "$SURFPOOL_MANAGED" == true ]]; then
    if ! command -v surfpool &>/dev/null; then
        echo "Error: surfpool not found. Install with: curl -sL https://run.surfpool.run/ | bash"
        exit 1
    fi

    # Kill any stale surfpool occupying our port
    STALE_PID=$(lsof -iTCP:"$SURFPOOL_PORT" -sTCP:LISTEN -t 2>/dev/null || true)
    if [[ -n "$STALE_PID" ]]; then
        echo "Port $SURFPOOL_PORT in use (pid $STALE_PID) — killing stale process..."
        kill "$STALE_PID" 2>/dev/null || true
        for _ in $(seq 1 20); do
            lsof -iTCP:"$SURFPOOL_PORT" -sTCP:LISTEN -t &>/dev/null || break
            sleep 0.5
        done
    fi

    echo "Starting surfpool (airdrop to $TEST_PUBKEY)..."
    surfpool start \
        --airdrop "$TEST_PUBKEY" \
        --airdrop-amount 100000000000 \
        --no-deploy \
        --no-tui \
        --no-studio > "$SURFPOOL_LOG" 2>&1 &
    SURFPOOL_PID=$!

    # Wait for RPC to be ready
    echo "Waiting for surfpool RPC..."
    for i in $(seq 1 30); do
        # Verify our surfpool process is still alive
        if ! kill -0 "$SURFPOOL_PID" 2>/dev/null; then
            echo "Error: surfpool crashed on startup. Log:"
            cat "$SURFPOOL_LOG"
            exit 1
        fi
        if curl -s "$SURFPOOL_RPC" -X POST \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
            2>/dev/null | grep -q "ok\|result"; then
            echo "Surfpool ready (pid $SURFPOOL_PID)."
            break
        fi
        if [[ $i -eq 30 ]]; then
            echo "Error: surfpool did not start within 30 seconds. Log:"
            cat "$SURFPOOL_LOG"
            exit 1
        fi
        sleep 1
    done
fi

# Export env vars for the test suite
export SURFPOOL_RPC
[[ -n "$MINT" ]] && export SURFPOOL_TEST_MINT="$MINT"
[[ -n "$GRADUATED_MINT" ]] && export SURFPOOL_GRADUATED_MINT="$GRADUATED_MINT"

echo ""
echo "=== Running surfpool integration tests ==="
echo "RPC: $SURFPOOL_RPC"
[[ -n "$MINT" ]] && echo "Mint: $MINT"
echo ""

uv run pytest tests/test_surfpool/ --surfpool -v "${EXTRA_ARGS[@]}"
