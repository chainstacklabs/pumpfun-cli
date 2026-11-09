# CLAUDE.md — pumpfun-cli

CLI for trading on pump.fun and Raydium LaunchLab launchpads (Solana), and launching on pump.fun. Python 3.12+, uv, Typer, solana-py/solders.

## Commands

```bash
# Install / sync
uv sync

# Run CLI (dev)
uv run pumpfun <command> [options]
uv run pumpfun --json <command>        # force JSON output

# Unit tests (always safe, no network)
uv run pytest tests/ -q
uv run pytest tests/ -v --cov          # with coverage
uv run pytest tests/test_core -v       # single module
uv run pytest tests/ -k test_name      # filter

# Surfpool integration (needs running surfpool daemon)
./scripts/surfpool-autodiscover.sh

# E2e mainnet (COSTS REAL SOL — always confirm with user first)
./scripts/mainnet-test.sh
./scripts/mainnet-test.sh --skip-trading
```

pytest is configured to auto-ignore `tests/test_surfpool/` by default. Surfpool and mainnet tests require explicit invocation.

## Architecture

Three-layer separation — never bypass layers:

```
commands/  →  core/  →  protocol/
  (thin)      (logic)    (Solana)
```

- **`commands/`** — Typer CLI wiring only. Parse args, call core, call `render()` or `error()`. All commands are async, bridged with `asyncio.run()`.
- **`core/`** — Framework-free business logic. Accept primitives (`rpc_url: str`, `password: str`, amounts). Return `dict` with results or `"error"` key for expected failures.
- **`protocol/`** — Pure Solana/pump.fun code. PDAs, RPC client, instruction builders, curve math, pool parsing. Zero business logic.

Entry point: `src/pumpfun_cli/cli.py` → `pyproject.toml` `[project.scripts] pumpfun = "pumpfun_cli.cli:app"`

## Project Structure

```
src/pumpfun_cli/
├── cli.py              # Root Typer app, GlobalState, callback, command registration
├── group.py            # JsonAwareGroup — allows --json at any argv position
├── crypto.py           # AES-256-GCM wallet encryption (scrypt KDF)
├── output.py           # render() + error() — TTY-aware output
├── commands/           # Thin CLI layer (config, info, launch, tokens, trade, tx_status, wallet)
├── core/               # Business logic (config, cpmm, info, launch, launchlab, pumpswap, tokens, trade, tx_status, validate, wallet)
└── protocol/           # Solana primitives (address, client, contracts, cpmm, curve, idl_parser, instructions, launchlab, pumpswap, quote)

tests/
├── test_commands/      # CLI smoke tests
├── test_core/          # Mocked business logic tests
├── test_protocol/      # Unit tests for protocol math/parsing
└── test_surfpool/      # Integration tests (ignored by default)
```

## Code Conventions

**Output:** Use `render(data, json_mode)` for all output — returns `True` if it emitted JSON (non-TTY or `--json`), `False` in TTY mode. Commands use `if not render(...):` to branch into human-readable output. Use `error(msg, hint, exit_code)` for failures — prints to stderr and raises `SystemExit`. Never use `print()`.

**Error handling:** `error()` raises `SystemExit` — code after it is unreachable. Core functions return `dict` with `"error"` key for expected failures (graduated tokens, not found, slippage exceeded, insufficient_balance). Catch `ValueError` for wrong wallet password in every command that decrypts. Buy/sell functions perform pre-trade balance validation — SOL for fees and rent, the quote asset for the spend, token balance for sells with specific amounts.

**Auto-routing:** `_route` in `commands/trade.py` picks the venue from the errors core returns: `{"error": "graduated"}` from `buy_token` / `sell_token` retries on PumpSwap, `{"error": "not_found"}` retries on LaunchLab (`buy_launchlab` / `sell_launchlab`), and LaunchLab's `graduated` retries on Raydium CPMM (`buy_cpmm` / `sell_cpmm`). `--force-amm` tries PumpSwap and falls back to CPMM only when PumpSwap reports no pool (`pool_missing`); PumpSwap's error stands unless CPMM recognises the coin as LaunchLab's. Never suppress or swallow those errors in core — the routing decision belongs in the command layer. `info` falls back to LaunchLab, and to its CPMM pool, the same way in `core/info.py`.

**Imports:** stdlib → third-party → local. Example:
```python
import asyncio
from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.core.config import resolve_value
from pumpfun_cli.output import render, error
```

**Naming:** `snake_case` functions/variables/files. `UPPER_CASE` constants. Prefix private helpers with `_`.

**Type hints:** Full type hints on all public function signatures.

**Async:** All I/O functions are `async def`. Commands bridge with `asyncio.run()`. `RpcClient` is stateless — always call `.close()` in `finally`.

**Config resolution:** `resolve_value(key, flag)` — flag > env var (via internal `ENV_MAP`) > config file > default.

## Adding a New Command

1. Add `core/my_feature.py` — `async def my_operation(rpc_url, keystore_path, password, ...) -> dict`
2. Add `commands/my_feature.py` — Typer wrapper that calls core and renders output
3. Register in `cli.py`:
   - Flat command: `app.command("my-command")(my_feature_cmd)`
   - Subcommand group: `app.add_typer(my_app, name="group-name")`
4. Add tests in `tests/test_core/test_my_feature.py` with mocked RPC/HTTP

## Working with Solana Accounts

```python
from pumpfun_cli.protocol.address import derive_bonding_curve
from pumpfun_cli.protocol.curve import parse_bonding_curve
from pumpfun_cli.protocol.instructions import build_buy_exact_quote_in_v2_instruction
from pumpfun_cli.protocol.quote import get_mint_info

resp = await client.get_account_info(derive_bonding_curve(mint))
state = parse_bonding_curve(bytes(resp.value.data))
quote_program, quote_decimals = await get_mint_info(client, state["quote_mint"])
ix = build_buy_exact_quote_in_v2_instruction(mint=mint, creator=state["creator"], ...)
sig = await client.send_tx([ix], [keypair], compute_units=..., confirm=True)
```

## Protocol rules

Read `docs/pumpfun-protocol.md` in pumpfun-bonkfun-bot before changing account
lists; these are the ones this CLI depends on.

- **Amounts are in the coin's quote asset**, read from `BondingCurve.quote_mint`
  (all zeros means SOL; instructions take wrapped SOL there). Its decimals come
  from the mint via `get_mint_info`; never assume 9.
- Bonding-curve trades use `buy_exact_quote_in_v2` / `sell_v2`: 27 / 26
  accounts, identical for every coin. A SOL coin's quote accounts are only
  seed-checked, so don't create the user's WSOL ATA for them.
- `creator_vault` derives from `BondingCurve.creator` as stored. On holder-reward
  and fee-sharing coins that is not the wallet that launched the coin.
- PumpSwap swaps carry accounts the IDL omits: cashback account(s) on a cashback
  pool, then `pool-v2` **only on a canonical pool** (`coin_creator` set), then the
  buyback recipient and its quote ATA last. The canonical pool is derived from the
  mint and the curve's quote mint.
- `migrate_v2` also carries accounts the IDL omits: after its 27, the new pool's
  boost vault authority (`["boost_vault", pool]` on PumpSwap) and that
  authority's quote token account. Without them PumpSwap reverts with 6027.
- LaunchLab (`protocol/launchlab.py`) pools are keyed by base and quote mint.
  The SOL pool is derived; any other quote is found by `getProgramAccounts`
  on the base mint (PoolState offset 205). Swaps are the IDL's 15 accounts plus
  the system program and the platform and creator fee vaults
  (`[platform_config, quote]`, `[creator, quote]`). The curve fee is
  GlobalConfig's trade fee plus PlatformConfig's fee and creator fee, read
  live; a Token-2022 coin's transfer fee comes off what arrives.
- A graduated LaunchLab coin's CPMM pool (`protocol/cpmm.py`) is derived from
  its PlatformConfig's `cpswap_config` and the two mints sorted by bytes.
  Reserves are the vault balances less the protocol, fund and creator fees the
  pool still owes. Both sides are `swap_base_input`, input token's accounts
  first. `migrate_type` 0 (AMM v4) is refused.
- `send_tx` sends v0 and falls back to v1 when the transaction exceeds 1232
  bytes (a cashback-pool buy, a launch with a buy). v1 carries the compute budget
  in its header.
- `create_v2` rejects cashback (6082). A creator fee only applies on a coin
  priced in a `QuoteControl` mint, and mayhem coins must be SOL-priced; launch
  refuses both before sending.

## Environment

```bash
PUMPFUN_RPC=https://...          # Solana RPC endpoint (required for trading)
PUMPFUN_KEYFILE=/path/to/...     # Path to encrypted wallet keystore
PUMPFUN_PRIORITY_FEE=200000      # Priority fee in micro-lamports
PUMPFUN_COMPUTE_UNITS=100000     # Compute unit limit
PUMPFUN_PASSWORD=...             # Wallet password (read directly in wallet commands, not via resolve_value)
```

Config file: `~/.config/pumpfun-cli/config.toml`
Wallet keystore: `~/.config/pumpfun-cli/wallet.enc`


## Hooks

Three hooks run automatically during Claude Code sessions (see `.claude/settings.json`):

- **guard.py** (PreToolUse → Write|Edit): Blocks edits to `.env`, `wallet.enc`, `idl/`, and credential files (`.pem`, `.key`, `.secret`). Edit these files manually.
- **lint.py** (PostToolUse → Write|Edit): Runs `ruff format` + `ruff check --fix` on every edited `.py` file. If unfixable errors remain, you will see them as errors — fix them before moving on.
- **bash-guard.py** (PreToolUse → Bash): Blocks `git add` of `docs/*.md` (exit 2). Otherwise advisory: adds a note to Claude's context (JSON `additionalContext`, never blocks) when commands send Solana transactions, run mainnet tests, or delete sensitive files. The CLI must work unimpeded when run via assistants or automated workflows.

## Boundaries

**Always do:**
- Run `uv run pytest tests/ -q` after code changes
- Follow the three-layer separation
- Use `render()` and `error()` for all CLI output
- Catch `ValueError` on wallet decryption
- Close `RpcClient` in `finally` blocks

**Ask first:**
- Running mainnet e2e tests (costs real SOL)
- Modifying `protocol/contracts.py` constants (program IDs, discriminators)
- Changing wallet encryption format in `crypto.py`

**Never do:**
- Bypass layers (commands must not import from protocol directly)
- Use `print()` instead of `render()`/`error()`
- Commit `.env` or wallet files
- Run mainnet tests without explicit user confirmation
- Add dependencies without discussing first
