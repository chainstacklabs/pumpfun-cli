# Stage 3: Implement Work Item #{{ITEM_NUMBER}}

You are implementing a work item for the pumpfun-cli project using TDD. Follow the plan exactly. Write tests first, then implement.

## Work Item

{{ITEM_DESCRIPTION}}

## Implementation Plan

{{PLAN_OUTPUT}}

## Project Root

`/home/antonsauchyk/Documents/pump-fun-projects/pumpfun-cli`

All commands run from this directory. Always use `uv run` prefix for Python/pytest commands.

## Project Conventions (MUST follow)

- **Architecture:** `commands/` → `core/` → `protocol/`. NEVER import from `protocol/` in `commands/`.
- **Output:** Use `render(data, json_mode)` and `error(msg, hint, exit_code)`. NEVER use `print()`.
- **Errors:** Core functions return `dict` with `"error"` key for expected failures. `error()` raises `SystemExit`.
- **Async:** All I/O functions are `async def`. Commands bridge with `asyncio.run()`. Close `RpcClient` in `finally` blocks.
- **Type hints:** Full type hints on all public function signatures.
- **Imports:** stdlib → third-party → local, separated by blank lines.
- **Naming:** `snake_case` functions/variables. `UPPER_CASE` constants. `_` prefix for private helpers.
- **Wallet decryption:** Catch `ValueError` in every command that decrypts the wallet.
- **Config resolution:** Use `resolve_value(key, env_var, flag)` — flag > env var > config file > default.

## TDD Process

### Phase 1: Create Feature Branch

```bash
git checkout main && git pull
git checkout -b feat/<item-slug> || git checkout feat/<item-slug>
```

Use a descriptive slug derived from the item title (e.g., `feat/pre-trade-balance-validation`). If the branch already exists (e.g., from a previous re-run), reuse it.

### Phase 2: Red — Write Failing Tests

Follow the Test Plan from the implementation plan. Write all unit tests first.

For each test file:
1. Write the test
2. Run it to confirm it fails: `uv run pytest tests/path/test_file.py::test_name -v`
3. Expected: FAIL (ImportError or AssertionError — the feature doesn't exist yet)

Test patterns to follow:
- **Core tests:** Mock RPC calls, test business logic in isolation
- **Command tests:** Use `typer.testing.CliRunner`, test CLI args/output/exit codes
- **Protocol tests:** Test pure functions (PDAs, math, parsing) with no mocking

### Phase 3: Green — Implement

Follow the Implementation Steps from the plan. Work bottom-up:

1. **protocol/** layer first (if needed) — pure functions, no business logic
2. **core/** layer — business logic, accepts primitives, returns dicts
3. **commands/** layer — thin Typer wiring, calls core, renders output
4. **cli.py** — register new commands if needed

After each layer, run the relevant tests:
```bash
uv run pytest tests/test_protocol/ -q   # after protocol changes
uv run pytest tests/test_core/ -q       # after core changes
uv run pytest tests/test_commands/ -q   # after command changes
```

### Phase 4: Full Suite

Run the complete unit test suite to catch regressions:
```bash
uv run pytest tests/ -q
```

ALL tests must pass. If any pre-existing test fails, fix the regression before proceeding.

## Output Format

When you are done, structure your final response as:

## Files Changed
<list every file you created or modified, one per line>

## Test Count After
<N> tests passing (from `uv run pytest tests/ -q` output)

## Summary
<brief description of what was implemented>

## CONSTRAINTS

- Follow the plan. Do not add features not in the plan.
- TDD: write tests BEFORE implementation.
- Run tests after every significant change.
- If tests cannot pass after 2 implementation attempts, STOP and report:
  - What tests are failing
  - What you tried
  - What you think the blocker is
- Do NOT run buy/sell/launch commands without `--dry-run`.
- Do NOT send Solana transactions.
- Do NOT modify `.env`, `wallet.enc`, or `protocol/contracts.py` constants.
- Do NOT add dependencies without noting it in your output.
