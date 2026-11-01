# pumpfun-cli

A standalone command-line tool for launching and trading tokens with the [pump.fun](https://pump.fun).

Built from experience developing [pumpfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot), distilled into a stateless CLI designed for humans, scripts, and LLM agents alike.

> Check out also our [skill](https://github.com/chainstacklabs/pumpclaw) for trading on pump.fun with OpenClaw and other agents.

Works on macOS, Linux, and Windows (via [WSL](https://learn.microsoft.com/en-us/windows/wsl/install)). Native Windows is not tested.

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12+.

### From GitHub (recommended)

```bash
uv tool install git+https://github.com/chainstacklabs/pumpfun-cli.git
```

This installs `pumpfun` globally — available from any directory.

### From a local clone

```bash
git clone https://github.com/chainstacklabs/pumpfun-cli.git
cd pumpfun-cli
uv tool install .
```

### Upgrade

```bash
# From GitHub
uv tool install --force git+https://github.com/chainstacklabs/pumpfun-cli.git

# From local clone (after git pull)
uv tool install --force .
```

### Uninstall

```bash
uv tool uninstall pumpfun-cli
```

## Quick start

```bash
# Browse tokens — works immediately, no config needed
pumpfun tokens trending
pumpfun tokens search "dog"

# Set up for trading
pumpfun config set rpc https://your-node.chainstack.com/abc123
pumpfun wallet create

# Preview a trade (no transaction sent)
pumpfun buy <mint> 0.1 --dry-run

# Trade
pumpfun buy <mint> 0.1
pumpfun sell <mint> all

# Check if a transaction landed
pumpfun tx-status <signature>

# Launch a token, buying it in the same transaction
pumpfun launch --name "MyToken" --ticker "MTK" --uri https://example.com/mytoken.json --buy 0.1
```

pump.fun no longer accepts anonymous metadata uploads, so `launch` takes the
URI of a metadata JSON you host (`name`, `symbol`, `description`, `image`).
Without `--uri` it still tries the upload and says so when it is refused.

Amounts are in the coin's quote asset. Most pump.fun coins are priced in SOL,
but a coin can be priced in USDC or another admitted mint; `buy`, `sell` and
`info` read it from the coin and label their output with it. Buying such a coin
spends that asset, so the wallet has to hold it.

In `--json` output an exact amount comes twice: in whole units for reading
(`tokens_sold`) and as the integer in raw units (`tokens_sold_raw`). Use the
`_raw` field for anything that has to add up; the float can drop a unit. An
amount known only as an estimate has no `_raw` twin: `quote_received`, the
`collect-creator-fee` totals, and `tokens_received` unless the buy ran with
`--confirm`, in which case it is read from the confirmed transaction. If that
transaction cannot be read back, a confirmed buy also reports the estimate
without `tokens_received_raw`, so check for the field. Dry-run fields
(`expected_tokens_raw`, `expected_quote_raw`, `min_*_out_raw`) are exact
integers of the quote the transaction would be built from, not executed amounts.

## Commands

```
Token discovery (zero config; price and progress added when an RPC is set):
  pumpfun tokens trending [--limit N]     pump.fun's movers board
  pumpfun tokens new [--limit N]          Recently launched
  pumpfun tokens graduating [--limit N]   Closest to bonding curve completion
  pumpfun tokens recommended [--limit N]  Recommended by pump.fun (at most 10)
  pumpfun tokens search <query>           Search by name or ticker

Token info (requires RPC):
  pumpfun info <mint>                     Price, bonding progress, reserves

Trading (requires RPC + wallet):
  pumpfun buy <mint> <amount> [--slippage N] [--force-amm] [--dry-run] [--confirm]
  pumpfun sell <mint> <amount|all> [--slippage N] [--force-amm] [--dry-run] [--confirm]
  pumpfun migrate <mint> [--confirm]
  pumpfun claim-cashback [--quote-mint M] [--confirm]
  pumpfun collect-creator-fee [--quote-mint M] [--confirm]
  pumpfun close-volume-acc [--confirm]

Transaction inspection (requires RPC):
  pumpfun tx-status <signature>              Confirmation status, slot, fee, errors

Token launch (requires RPC + wallet):
  pumpfun launch --name X --ticker Y [--uri U | --desc D --image P] [--buy N]
                 [--quote-mint M] [--creator-fee-bps N] [--holder-reward]
                 [--mayhem] [--slippage N] [--confirm]

Wallet management:
  pumpfun wallet create                   Generate + encrypt keypair
  pumpfun wallet import <keypair.json>    Import existing keypair
  pumpfun wallet show                     Display public key
  pumpfun wallet balance                  SOL + token balances
  pumpfun wallet transfer <to> <amount>   Transfer SOL or tokens (--mint for SPL)
  pumpfun wallet drain <recipient>        Close all ATAs + transfer remaining SOL
  pumpfun wallet export --output <path>   Export as Solana keypair JSON

Config:
  pumpfun config set <key> <value>
  pumpfun config get <key>
  pumpfun config list

Global options:
  --version           Show version and exit
  --json              Machine-readable JSON output
  --rpc <url>         Override RPC endpoint
  --keyfile           Override wallet keystore path
  --priority-fee N    Priority fee in micro-lamports (overrides default)
  --compute-units N   Compute unit limit (overrides default)
```

## Endpoints

| Command | Endpoint | Protocol |
|---------|----------|----------|
| `tokens trending` | `frontend-api-v3.pump.fun/coins/boards/movers` | HTTPS |
| `tokens new` | `frontend-api-v3.pump.fun/coins/boards/new` | HTTPS |
| `tokens graduating` | `frontend-api-v3.pump.fun/coins/boards/graduating` | HTTPS |
| `tokens recommended` | `frontend-api-v3.pump.fun/coins/recommendations` | HTTPS |
| `tokens search` | `frontend-api-v3.pump.fun/coins/search-unrestricted` | HTTPS |
| `tokens *` with an RPC set | + Solana RPC (`getMultipleAccounts` for the bonding curves) | JSON-RPC |
| `info` | Solana RPC (`getAccountInfo` for bonding curve PDA) | JSON-RPC |
| `buy` | Solana RPC (`getAccountInfo`, `getLatestBlockhash`, `sendTransaction`) | JSON-RPC |
| `sell` | Solana RPC (`getAccountInfo`, `getTokenAccountBalance`, `getLatestBlockhash`, `sendTransaction`) | JSON-RPC |
| `launch` | Solana RPC (`sendTransaction`); `pump.fun/api/ipfs` only without `--uri` | JSON-RPC (+ HTTPS) |
| `tx-status` | Solana RPC (`getTransaction`) | JSON-RPC |
| `migrate` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `claim-cashback` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `collect-creator-fee` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `close-volume-acc` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `wallet balance` | Solana RPC (`getBalance`, `getTokenAccountsByOwner`) | JSON-RPC |
| `wallet transfer` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `wallet drain` | Solana RPC (`getTokenAccountsByOwner`, `sendTransaction`) | JSON-RPC |
| `wallet create/show/import/export` | None (local keystore only) | — |
| `config *` | None (local config file only) | — |

The `tokens` listings use pump.fun's frontend API, which is unofficial and
changes without notice. They are narrowed to pump.fun coins on Solana; the API
no longer returns curve reserves, so price and bonding progress come from the
chain and need an RPC endpoint.

## Security

- Private keys are encrypted at rest (AES-256-GCM + scrypt)
- Password required for any key operation
- Keys never appear in stdout, stderr, or logs
- `wallet export` requires explicit `--output` flag

## Architecture

Three-layer separation:

- **commands/** — Thin Typer CLI wiring
- **core/** — Framework-free business logic
- **protocol/** — Pure Solana/pump.fun protocol code

## Testing

Unit tests run without any external dependencies:

```bash
uv run pytest
```

### Integration tests with Surfpool

For testing transactions against real pump.fun program state, we use [Surfpool](https://www.surfpool.run/) — a local Solana fork that lazily loads accounts from mainnet. This is optional.

```bash
# Install surfpool
curl -sL https://run.surfpool.run/ | bash

# Run integration tests (starts/stops surfpool automatically)
./scripts/surfpool-test.sh --mint <ACTIVE_BONDING_CURVE_MINT>

# Optionally test graduated token handling too
./scripts/surfpool-test.sh --mint <ACTIVE_MINT> --graduated <GRADUATED_MINT>

# Or if surfpool is already running
./scripts/surfpool-test.sh --running --mint <MINT>
```

Surfpool forks mainnet state on demand — no need to manually clone programs or accounts. The tests validate info retrieval, buy, sell, and error handling against the actual pump.fun program.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, architecture, and how to submit changes.

## Agentic Coding

This repo is configured for AI coding agents via the `.claude/` directory:

- **`CLAUDE.md`** — project context, commands, conventions, and boundaries
- **`hooks/`** — auto-lint on edit, guard against writing secrets, warn on transaction commands
- **`skills/`** — workflows for test automation

### Skills

The `.claude/skills/` directory contains [Agent Skills](https://agentskills.io/home) — an open standard for extending AI coding agents with reusable, modular capabilities.

| Skill | Purpose |
|-------|---------|
| `run-unit-and-surfpool-tests` | Run unit tests + optional Surfpool integration tests |
| `run-mainnet-e2e-tests` | Run end-to-end tests against Solana mainnet (costs real SOL) |
| `work-item` | Investigate, plan, implement (TDD), verify, and finalize work items as PRs |

**Cross-agent portability.** The Agent Skills format was [originated by Anthropic](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) and released as an open standard. It has since been adopted by [OpenAI Codex](https://developers.openai.com/codex/skills/), [GitHub Copilot](https://code.visualstudio.com/docs/copilot/customization/custom-instructions), [Cursor](https://cursor.com/docs/context/rules), and others. Any agent that can read a directory and parse Markdown can use them.

### Instructions file

`CLAUDE.md` is read natively by [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and by [GitHub Copilot in VS Code](https://code.visualstudio.com/docs/copilot/customization/custom-instructions#_use-a-claudemd-file). `AGENTS.md` is provided as a symlink to `CLAUDE.md` — an open format supported by Codex, Cursor, Copilot, and others.
