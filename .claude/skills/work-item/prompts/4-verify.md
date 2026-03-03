# Stage 4: Verify Work Item #{{ITEM_NUMBER}}

You are verifying the implementation of a work item for the pumpfun-cli project. Run the full test suite, integration tests if needed, and manually smoke-test the new feature.

## Work Item

{{ITEM_DESCRIPTION}}

## Files Changed

{{FILES_CHANGED}}

## Test Tiers to Run

{{TEST_TIERS}}

## Baseline

- Tests before implementation: {{TEST_COUNT_BEFORE}}
- Tests after implementation: {{TEST_COUNT_AFTER}}

## Project Root

`/home/antonsauchyk/Documents/pump-fun-projects/pumpfun-cli`

All commands run from this directory. Always use `uv run` prefix for Python/pytest commands.

## Verification Steps

### 1. Unit Tests (always run)

```bash
uv run pytest tests/ -q
```

Record the pass/fail count. If ANY test fails, report the failure with file:line and stop — do not proceed to surfpool or smoke testing.

### 2. Surfpool Integration Tests (if "surfpool" is in Test Tiers)

```bash
./scripts/surfpool-autodiscover.sh
```

This auto-discovers mints, starts surfpool, runs integration tests, stops surfpool. Record pass/fail count. `xfail` results are expected and not failures.

If surfpool is not available (binary not installed), note this and skip.

### 3. Mainnet E2E Tests (if "mainnet" is in Test Tiers)

**STOP. Do NOT run mainnet tests without explicit user approval.** Report:
> "Mainnet testing is flagged for this item. This costs real SOL. Please confirm you want to proceed."

If approved: `./scripts/mainnet-test.sh`

### 4. Regression Check

Compare test counts:
- Before: {{TEST_COUNT_BEFORE}}
- Current: <count from step 1>
- Delta: should be positive (new tests added)

If current count is LOWER than before, there is a regression. Report which tests are missing.

### 5. Manual Smoke Test

Run the CLI to exercise the new feature. Use safe commands only:
- Read-only commands (info, balance, tokens, config) — always safe
- Trading commands ONLY with `--dry-run` flag
- JSON mode: `uv run pumpfun --json <command>`
- Environment: `PUMPFUN_RPC` is in `.env`, `PUMPFUN_PASSWORD=testpass123`

Design 3-5 smoke test commands that cover:
- The happy path (feature works as expected)
- An error case (feature returns proper error)
- JSON output mode (structured output is correct)

## Output Format

Structure your response EXACTLY as follows:

## Unit Tests
**Result:** <N passed, M failed>
<if failures: list each with file:line and error message>

## Surfpool Tests
**Result:** <N passed, M failed, K xfailed> or "Skipped (not in test tiers)" or "Skipped (surfpool not available)"

## Mainnet Tests
**Result:** <results> or "Not required for this item" or "Awaiting user approval"

## Manual Smoke Test
<For each command:>
### Command: `<exact command>`
**Expected:** <what should happen>
**Actual:** <what happened — include output>
**Status:** PASS / FAIL

## Regression Check
- Before: {{TEST_COUNT_BEFORE}} tests
- After: <current count> tests
- Delta: +<N> tests
- Regressions: <none, or list of failing tests that previously passed>

## CONSTRAINTS

- Do NOT edit any files. You are verifying, not fixing.
- Do NOT send Solana transactions (no buy/sell/launch without --dry-run).
- Do NOT run mainnet tests without user approval.
- If you find failures, report them clearly — do not attempt to fix them.
