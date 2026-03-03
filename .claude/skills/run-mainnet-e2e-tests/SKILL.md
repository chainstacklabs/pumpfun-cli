---
name: run-mainnet-e2e-tests
description: Run end-to-end tests for pumpfun-cli against Solana mainnet. Use this skill when the user asks for "e2e tests", "end to end tests", "test on mainnet", "QA the CLI", "test with real transactions", or "smoke test against mainnet". WARNING - this skill executes real transactions that cost real SOL. Only use when the user explicitly wants mainnet testing. For safe/free tests use the run-unit-and-surfpool-tests skill instead.
---

# E2E QA Agent for pumpfun-cli

You are acting as a QA engineer testing pumpfun-cli against Solana mainnet with real transactions.

## CRITICAL WARNING

This skill spends real SOL on mainnet. Before starting:
1. Confirm with the user they want mainnet e2e testing
2. Show the wallet balance and ask for approval
3. Keep trade amounts minimal (0.001 SOL per trade)

## Prerequisites

Run the prereq checker from the project root:

```bash
bash .claude/skills/run-mainnet-e2e-tests/scripts/check-prereqs.sh
```

If any check fails, fix it before proceeding. The script will show the wallet pubkey and balance.

Environment setup (if needed):
```bash
export PUMPFUN_RPC="$(grep PUMPFUN_RPC .env | cut -d= -f2)"
export PUMPFUN_PASSWORD="<wallet-password>"
```

## Test Plan

### Automated (recommended)

Run the full e2e suite via the helper script:

```bash
./scripts/mainnet-test.sh                # full run including trading (spends SOL)
./scripts/mainnet-test.sh --skip-trading # safe-only groups (no SOL spent)
```

The script auto-discovers mints, runs all 11 groups, handles retries for known timing issues, and writes results to `docs/e2e-test-results.md`.

### Manual (for debugging or selective testing)

Read `references/manual-test-groups.md` for the full manual test plan with all 11 groups, exact commands, safety labels, and testing insights.

## Output Format

Follow the template in `references/report-template.md`. Write results to `docs/e2e-test-results.md`.

## Decision Tree for Failures

- **Exit code 1 + error message** -- expected error handling, record as PASS if the message is correct
- **Exit code 0 but wrong output** -- BUG, document with full output
- **"Transaction confirmed but failed"** -- on-chain failure, record error code and check known issues
- **Timeout/hang** -- kill after 30s, record as ISSUE with the command that hung
- **"No tokens to sell" after buy** -- known RPC lag, wait 5s and retry once before recording as ISSUE
- **Error 6023 on PumpSwap** -- known BUG-1, record and move on

## Known Issues

Check `docs/e2e-test-results.md` for previously documented issues from past runs. Compare your results against them -- note if issues are now fixed or if new ones appeared.

## When to use this skill vs run-unit-and-surfpool-tests

Use **run-unit-and-surfpool-tests** for fast, free, offline unit/integration tests. Use **run-mainnet-e2e-tests** only when you need to verify real on-chain behavior against Solana mainnet -- it costs SOL and is slower.
