#!/usr/bin/env bash
# Convenience wrapper around surfpool-test.sh that auto-discovers mints.
#
# Instead of manually finding and passing --mint / --graduated flags,
# this script queries the pump.fun API to find suitable tokens, then
# delegates to surfpool-test.sh with the discovered mints.
#
# Usage:
#   ./scripts/surfpool-autodiscover.sh
#
# If you already know the mints, skip this and call surfpool-test.sh directly:
#   ./scripts/surfpool-test.sh --mint <MINT> --graduated <GRADUATED_MINT>
#
# Prerequisites:
#   - surfpool installed
#   - uv sync --group dev
#   - .env with PUMPFUN_RPC set (for mint discovery via mainnet API)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Load RPC from .env if present
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

if [[ -z "${PUMPFUN_RPC:-}" ]]; then
    echo "Error: PUMPFUN_RPC not set. Create .env or export it."
    exit 1
fi

if ! command -v surfpool &>/dev/null; then
    echo "Error: surfpool not found. Install with: curl -sL https://run.surfpool.run/ | bash"
    exit 1
fi

echo "Discovering active bonding-curve token..."
ACTIVE_MINT=$(uv run pumpfun tokens new --limit 10 2>/dev/null | uv run python3 -c "
import json, sys
tokens = json.load(sys.stdin)
for t in tokens:
    if not t.get('complete', True) and t.get('real_token_reserves', 0) > 0 and t.get('real_sol_reserves', 0) > 1_000_000_000:
        print(t['mint'])
        break
else:
    sys.exit(1)
" 2>/dev/null) || {
    echo "Error: Could not find an active bonding-curve token. The pump.fun API may be down."
    echo "Retry in a minute, or pass mints manually:"
    echo "  ./scripts/surfpool-test.sh --mint <MINT> --graduated <GRADUATED_MINT>"
    exit 1
}
echo "  Active mint: $ACTIVE_MINT"

echo "Discovering graduated PumpSwap token..."
GRADUATED_MINT=$(uv run pumpfun tokens trending --limit 10 2>/dev/null | uv run python3 -c "
import json, sys
tokens = json.load(sys.stdin)
for t in tokens:
    if t.get('complete') and t.get('pump_swap_pool'):
        print(t['mint'])
        break
else:
    sys.exit(1)
" 2>/dev/null) || {
    echo "Error: Could not find a graduated PumpSwap token. The pump.fun API may be down."
    echo "Retry in a minute, or pass mints manually:"
    echo "  ./scripts/surfpool-test.sh --mint <MINT> --graduated <GRADUATED_MINT>"
    exit 1
}
echo "  Graduated mint: $GRADUATED_MINT"

echo ""
echo "Running surfpool tests with discovered mints..."
exec "$SCRIPT_DIR/surfpool-test.sh" --mint "$ACTIVE_MINT" --graduated "$GRADUATED_MINT" "$@"
