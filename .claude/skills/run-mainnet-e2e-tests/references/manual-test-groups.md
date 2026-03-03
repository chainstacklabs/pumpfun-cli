# Manual Test Groups (E2E QA)

This file contains the full manual test plan organized into Groups 1-11.
Use this for manual or selective testing when you need to debug specific
groups rather than running the full automated `scripts/mainnet-test.sh`.

Work through each group in order. For each test, record PASS/FAIL/ISSUE and any relevant output.

---

## Group 1: Wallet (read-only, safe)

```bash
uv run pumpfun wallet show
uv run pumpfun wallet balance
uv run pumpfun wallet tokens
uv run pumpfun --json wallet balance          # JSON mode
uv run pumpfun wallet show --keyfile /tmp/x   # should error: "No wallet found"
PUMPFUN_PASSWORD=wrongpass uv run pumpfun wallet export --output /tmp/x  # should error
```

## Group 2: Config (safe)

```bash
uv run pumpfun config set e2e_test_key e2e_value
uv run pumpfun config get e2e_test_key        # should return "e2e_value"
uv run pumpfun config list                    # should include e2e_test_key
uv run pumpfun config delete e2e_test_key
uv run pumpfun config get e2e_test_key        # should error: "Key not set" (exit 1)
```

## Group 3: Token Discovery (safe, API-only)

```bash
uv run pumpfun tokens trending --limit 3
uv run pumpfun tokens new --limit 3
uv run pumpfun tokens graduating --limit 3
uv run pumpfun tokens recommended --limit 3
uv run pumpfun tokens search "sol" --limit 3  # may return empty — known issue
```

Validate: each returns valid JSON arrays, non-empty (except search which may be empty).

## Group 4: Token Info (read-only RPC)

Find an active bonding-curve mint and a graduated mint from the discovery results above.

```bash
uv run pumpfun info <ACTIVE_MINT>             # graduated=false, price_sol > 0
uv run pumpfun info <GRADUATED_MINT>          # graduated=true, pool_address present
uv run pumpfun info 11111111111111111111111111111111  # should error
```

## Group 5: Dry-Run & Balance Validation (safe, no SOL spent)

Pick an active bonding-curve token from `tokens new`.

```bash
# Dry-run buy — simulates trade, shows expected tokens and price impact
uv run pumpfun --json buy <ACTIVE_MINT> 0.001 --dry-run

# Dry-run sell — simulates sell (will show balance_warning if no tokens held)
uv run pumpfun --json sell <ACTIVE_MINT> 1000 --dry-run

# Insufficient balance — should return structured error without sending tx
uv run pumpfun --json buy <ACTIVE_MINT> 999999 2>&1 || true
```

Validate: dry-run returns JSON with `dry_run: true`, expected fields, and optional `balance_warning`. Insufficient balance returns `{"error": "...insufficient..."}` with exit code 1.

## Group 6: Bonding Curve Trading (SPENDS SOL)

Pick an active bonding-curve token from `tokens new` (must have `complete: false` and `real_token_reserves > 0`).

```bash
# Buy with --confirm to verify on-chain success
uv run pumpfun buy <ACTIVE_MINT> 0.001 --confirm

# Check tokens arrived
uv run pumpfun wallet tokens

# IMPORTANT: wait 3-5 seconds for RPC state to propagate before selling.
# Selling immediately after buy often returns "No tokens to sell" due to RPC lag.
sleep 5

# Sell all
uv run pumpfun sell <ACTIVE_MINT> all --confirm
```

**Key insights from previous testing:**
- Always use `--confirm` for trades -- without it the CLI reports success even when the tx fails on-chain (BUG-2 in backlog)
- Add a ~5 second delay between buy and sell -- immediate sell after buy often fails with "No tokens to sell" due to RPC state lag (ISSUE-3)
- If sell fails, retry after a few seconds -- this is a known timing issue, not a code bug

## Group 7: PumpSwap AMM Trading (SPENDS SOL -- CURRENTLY BROKEN)

**Known bug:** PumpSwap buys consistently fail with error 6023 (NotEnoughTokensToSell). Test anyway to check if it has been fixed.

```bash
uv run pumpfun buy <GRADUATED_MINT> 0.001 --force-amm --confirm
uv run pumpfun buy <GRADUATED_MINT> 0.001 --confirm  # auto-route
```

If still failing with 6023, document and move on.

## Group 8: Transaction Status (safe, read-only RPC)

After any trade in Groups 6-7, use the signature to check status:

```bash
uv run pumpfun tx-status <SIGNATURE>              # human-readable output
uv run pumpfun --json tx-status <SIGNATURE>        # JSON output
uv run pumpfun tx-status not-a-valid-sig           # should error: "Invalid transaction signature"
uv run pumpfun --json tx-status 11111111111111111111111111111111111111111111111111111111111111111111111111111111111111  # should error: "not found"
```

Validate: confirmed transactions show status, slot, fee, explorer URL. Invalid signatures return structured error.

## Group 9: Extras (SPENDS SOL -- small gas only)

```bash
uv run pumpfun claim-cashback --confirm       # may succeed or be no-op
uv run pumpfun close-volume-acc --confirm     # may succeed or be no-op
uv run pumpfun collect-creator-fee --confirm  # likely "No creator fees"
uv run pumpfun migrate <ACTIVE_MINT> --confirm  # should error: "not complete"
```

## Group 10: Wallet Cleanup (SPENDS SOL -- recovers rent)

```bash
uv run pumpfun wallet close-atas --confirm    # close any empty ATAs left over
uv run pumpfun wallet balance                 # final balance check
```

## Group 11: CLI Options & Help (safe)

```bash
uv run pumpfun --help
uv run pumpfun wallet --help
uv run pumpfun tokens --help
uv run pumpfun buy --help
uv run pumpfun wallet balance | python3 -c "import json,sys; json.load(sys.stdin)"  # pipe JSON valid
```
