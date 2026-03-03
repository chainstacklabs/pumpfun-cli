# Stage 1: Investigate Work Item #{{ITEM_NUMBER}}

You are investigating a work item for the pumpfun-cli project before any code changes are made.

## Work Item

{{ITEM_DESCRIPTION}}

## Your Task

Investigate the current codebase and CLI behavior to understand the gap this work item addresses. You must NOT edit any files. You must NOT send transactions or spend SOL.

## Project Context

- **Root:** `/home/antonsauchyk/Documents/pump-fun-projects/pumpfun-cli`
- **Source:** `src/pumpfun_cli/`
- **Architecture:** `commands/` (Typer CLI) → `core/` (business logic) → `protocol/` (Solana)
- **Tests:** `tests/` (unit), `tests/test_surfpool/` (integration)
- **Run CLI:** `uv run pumpfun <command>`
- **Run tests:** `uv run pytest tests/ -q`
- **Config:** `CLAUDE.md` has full conventions

## Steps

1. **Read the affected files** listed in the work item's "Scope" field. Also read `CLAUDE.md` for project conventions.
2. **Trace the current code path.** For example, if the item is about buy validation, trace what happens from `commands/trade.py` → `core/trade.py` → `protocol/client.py` when a buy is executed. Note specific file:line references.
3. **Demonstrate current behavior.** Run the CLI with safe, read-only commands to show what happens today. Examples:
   - `uv run pumpfun info <mint>` (always safe)
   - `uv run pumpfun wallet balance` (always safe)
   - `uv run pumpfun buy <mint> 0.001 --dry-run` (safe — dry-run, if available)
   - `uv run pumpfun --json <command>` (to see JSON output)
   - NEVER run buy/sell/launch without `--dry-run`
   - If `--dry-run` is not yet implemented, skip trade command demos and note this limitation
   - Environment: `PUMPFUN_RPC` is in `.env`, `PUMPFUN_PASSWORD=testpass123`
4. **Identify edge cases** that the implementation must handle.
5. **Capture the baseline test count:** Run `uv run pytest tests/ -q` and note the "N passed" count.
6. **Determine test tiers needed:**
   - **Unit** (always): mocked tests in `tests/test_core/`, `tests/test_commands/`, `tests/test_protocol/`
   - **Surfpool** (if touches RPC/transaction logic): integration tests in `tests/test_surfpool/`
   - **Mainnet** (rare — only if surfpool cannot cover it): e2e via `./scripts/mainnet-test.sh`
7. **Check for combinable items.** Read `docs/work-items.md` and check if any other undone item shares >50% of the same code path. If so, recommend combining.

## Output Format

Structure your response EXACTLY as follows:

## Current Behavior
<what happens today — include actual CLI output from your demo commands>

## Gap Analysis
<what's missing or broken, with specific file:line references>

## Affected Files
**protocol/**: <list files>
**core/**: <list files>
**commands/**: <list files>
**tests/**: <list expected test files>

## Edge Cases
1. <edge case 1>
2. <edge case 2>
...

## Test Tiers Needed
<unit / surfpool / mainnet — with one sentence of reasoning per tier>

## Baseline Test Count
<N> tests currently passing

## Combine Recommendation
<"None" or "Recommend combining with #N because: <rationale>">

## CONSTRAINTS — DO NOT VIOLATE

- **DO NOT** edit, create, or delete any files
- **DO NOT** run buy/sell/launch commands without `--dry-run`
- **DO NOT** send any Solana transactions
- **DO NOT** modify the wallet or config
- You are read-only. Your job is to investigate and report, not to fix.
