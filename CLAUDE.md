# CLAUDE.md — pumpfun-cli

CLI for trading, launching, and browsing tokens on pump.fun (Solana). Python 3.12+, uv, Typer, solana-py/solders.

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
├── core/               # Business logic (config, info, launch, pumpswap, tokens, trade, tx_status, validate, wallet)
└── protocol/           # Solana primitives (address, client, contracts, curve, idl_parser, instructions, pumpswap)

tests/
├── test_commands/      # CLI smoke tests
├── test_core/          # Mocked business logic tests
├── test_protocol/      # Unit tests for protocol math/parsing
└── test_surfpool/      # Integration tests (ignored by default)
```

## Code Conventions

**Output:** Use `render(data, json_mode)` for all output — returns `True` if it emitted JSON (non-TTY or `--json`), `False` in TTY mode. Commands use `if not render(...):` to branch into human-readable output. Use `error(msg, hint, exit_code)` for failures — prints to stderr and raises `SystemExit`. Never use `print()`.

**Error handling:** `error()` raises `SystemExit` — code after it is unreachable. Core functions return `dict` with `"error"` key for expected failures (graduated tokens, not found, slippage exceeded, insufficient_balance). Catch `ValueError` for wrong wallet password in every command that decrypts. Buy/sell functions perform pre-trade balance validation — SOL balance for buys (including fees + ATA rent), token balance for sells with specific amounts.

**Auto-routing:** When `buy_token` / `sell_token` returns `{"error": "graduated"}`, the command layer in `commands/trade.py` automatically retries via `buy_pumpswap` / `sell_pumpswap` (PumpSwap AMM). Never suppress or swallow the `"graduated"` error in core — the routing decision belongs in the command layer.

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
# Derive PDA
from pumpfun_cli.protocol.address import derive_bonding_curve

# Fetch and decode
data = await client.get_account_data(address)
state = idl.decode_account_data(data, "BondingCurve", skip_discriminator=True)

# Build instructions
from pumpfun_cli.protocol.instructions import build_buy_exact_sol_in_instructions
ixs = build_buy_exact_sol_in_instructions(idl=idl, mint=mint, user=keypair.pubkey(), ...)
sig = await client.send_tx(ixs, [keypair], compute_units=..., confirm=True)
```

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
- **bash-guard.py** (PreToolUse → Bash): Advisory only — prints warnings (never blocks) when commands send Solana transactions, run mainnet tests, or delete sensitive files. The CLI must work unimpeded when run via assistants or automated workflows.

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
