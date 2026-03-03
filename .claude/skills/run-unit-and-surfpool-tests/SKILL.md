---
name: run-unit-and-surfpool-tests
description: Run pumpfun-cli test suites — unit tests and surfpool integration tests. Use this skill whenever the user says "run tests", "run unit tests", "run surfpool tests", "check if tests pass", "test the code", or after making code changes that should be verified. Also trigger when the user asks to validate changes, check for regressions, or verify something works. This skill covers ALL non-mainnet testing. For mainnet e2e testing with real funds, use the run-mainnet-e2e-tests skill instead.
---

# Test Runner for pumpfun-cli

Run the project's automated test suites safely — no real funds, no mainnet transactions.

## Project Context

- **Package manager:** `uv` (always prefix python/pytest commands with `uv run`)
- **Architecture:** Three-layer CLI — `commands/` (Typer) -> `core/` (business logic) -> `protocol/` (Solana/pump.fun)
- All commands below assume you are in the project root directory.

## Prerequisites

Run the check-prereqs script from the skill directory before doing anything else:

```bash
.claude/skills/run-unit-and-surfpool-tests/scripts/check-prereqs.sh
```

If it exits non-zero, fix the FAIL items before proceeding. WARN items (e.g. surfpool missing) are fine for unit tests.

## Two Test Suites

### 1. Unit Tests (fast, always safe)

Tests covering crypto, wallet, trade logic, protocol, output formatting, and CLI smoke tests. All mocked — no network calls. Run and report actual counts.

```bash
uv run pytest tests/ -q
```

Run this first every time. If unit tests fail, stop and report — no point running integration tests on broken code.

### 2. Surfpool Integration Tests (slower, needs surfpool + mainnet mints)

Tests that run against a local Surfpool fork of Solana mainnet. Surfpool replays mainnet state locally so transactions are free and reversible. Run and report actual counts.

**How to run — use the helper script from the project root:**

```bash
./scripts/surfpool-autodiscover.sh
```

This script automatically:
1. Discovers a suitable active bonding-curve mint via `tokens new`
2. Discovers a suitable graduated PumpSwap mint via `tokens trending`
3. Starts surfpool, runs all tests, stops surfpool

**Manual run (if you need specific mints):**

```bash
./scripts/surfpool-test.sh \
  --mint <ACTIVE_BONDING_CURVE_MINT> \
  --graduated <GRADUATED_PUMPSWAP_MINT>
```

## Execution Sequence

Follow this order:

1. **Check prerequisites** — `.claude/skills/run-unit-and-surfpool-tests/scripts/check-prereqs.sh`
2. **Run unit tests** — `uv run pytest tests/ -q`
3. **Check result** — if any fail, report failures with file:line and stop
4. **Run surfpool tests** (if surfpool available) — `./scripts/surfpool-autodiscover.sh`
5. **Report results** — use the template at `.claude/skills/run-unit-and-surfpool-tests/references/results-template.md` for consistent formatting

## Failure Diagnosis

When tests fail, use this decision tree to diagnose:

- **Unit test assertion failure** — Read the failing test to understand what it checks. Then read the production code it exercises. The assertion tells you what the expected behavior is; the code tells you what changed.

- **Import error / ModuleNotFoundError** — Likely a missing or renamed dependency. Check `pyproject.toml` for the package. Run `uv sync` if a dependency was recently added.

- **Surfpool connection refused (ConnectionRefusedError, "Connection refused" on port 8899)** — Surfpool is not running, or another process holds port 8899. Check with `lsof -ti:8899`. Kill stale processes if needed: `lsof -ti:8899 | xargs kill -9`, then retry.

- **Surfpool tests skipped** — Missing environment variables for mint addresses. The autodiscover script should set these. If running manually, ensure `--mint` and `--graduated` are provided.

- **xfail (expected failure)** — This is normal and not a problem. The test is marked as known-flaky or testing a known limitation.

- **Mint discovery failure** — The pump.fun API may be down or no suitable tokens exist. Retry after a minute.

## Known Behaviors

- **Expected xfail:** `test_buy_then_sell_pumpswap` is marked `@pytest.mark.xfail` because PumpSwap buy/sell on forked state often hits slippage issues. If it xfails, that's normal.
- **surfpool-test.sh** uses `uv run python3` (not bare `python3`) because solders/solana packages are in the uv venv.

## Interpreting Results

| Result | Meaning |
|--------|---------|
| All unit tests pass | Core logic is sound |
| Surfpool all pass + xfails only | Full integration suite healthy |
| Surfpool skips | Missing `--mint` or `--graduated` env vars (the auto script should prevent this) |
| Unit test failures | Regression in core logic — fix before anything else |
| Surfpool failures (not xfail) | Possible protocol change or instruction bug — investigate |

## Reporting

Use the template at `.claude/skills/run-unit-and-surfpool-tests/references/results-template.md` for a standardized report. Fill in actual counts from the test run. Include the failed-test table only when there are failures.
