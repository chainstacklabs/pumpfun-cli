<img width="1200" alt="Labs" src="https://user-images.githubusercontent.com/99700157/213291931-5a822628-5b8a-4768-980d-65f324985d32.png">

<p>
 <h3 align="center">Chainstack is the leading suite of services connecting developers with Web3 infrastructure</h3>
</p>

<p align="center">
  • <a target="_blank" href="https://chainstack.com/">Homepage</a> •
  <a target="_blank" href="https://chainstack.com/protocols/">Supported protocols</a> •
  <a target="_blank" href="https://chainstack.com/blog/">Chainstack blog</a> •
  <a target="_blank" href="https://docs.chainstack.com/reference/blockchain-apis">Blockchain API reference</a> • <br> 
  • <a target="_blank" href="https://console.chainstack.com/user/account/create">Start for free</a> •
</p>

A stateless command-line tool for trading on **pump.fun** and on **letsbonk.fun**, **StonkFun** and every other launchpad on Raydium LaunchLab. It buys and sells on the bonding curve, follows graduated coins into PumpSwap and Raydium CPMM, and launches pump.fun coins. Built for humans, scripts and AI agents alike: every command can answer in JSON.

It is distilled from [pumpfun-bonkfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot) and works on macOS, Linux and Windows through [WSL](https://learn.microsoft.com/en-us/windows/wsl/install); native Windows is not tested.

> **Also by Chainstack**
> - [**pumpfun-bonkfun-bot**](https://github.com/chainstacklabs/pumpfun-bonkfun-bot) — trading and sniping bot for the same venues: watches for new coins, buys, and exits on a strategy you configure.
> - [**pumpclaw**](https://github.com/chainstacklabs/pumpclaw) — agent skill that equips AI assistants (OpenClaw, Claude Code, Cursor, Codex) with the ability to operate this CLI.

---

**🚨 SCAM ALERT**: The Issues section is regularly targeted by scam bots that try to redirect you to an external site and drain your funds. Deleted comments in issues are scam bots after your private keys — genuine outside devs are welcome and appreciated.

**⚠️ NOT FOR PRODUCTION**: This code is for learning purposes only. We assume no responsibility for the code or its usage. Every trade spends real funds; preview it with `--dry-run` first.

---

## Getting started

### 1. Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). The CLI needs **Python 3.12+**; `uv` uses an existing install if it's new enough, otherwise it fetches one for you.

You also need a Solana RPC endpoint for anything that reads or writes the chain. Public RPC nodes won't hold up — see [throughput](#throughput-and-rate-limits) below.

### 2. Install

```bash
uv tool install git+https://github.com/chainstacklabs/pumpfun-cli.git
```

This puts `pumpfun` on your path, available from any directory. To install from a clone instead, run `uv tool install .` in it.

```bash
uv tool install --force git+https://github.com/chainstacklabs/pumpfun-cli.git   # upgrade
uv tool uninstall pumpfun-cli                                                  # remove
```

### 3. Set your RPC endpoint and wallet

```bash
pumpfun config set rpc https://your-node.chainstack.com/abc123
pumpfun wallet create            # or: pumpfun wallet import <keypair.json>
```

The wallet is stored encrypted in `~/.config/pumpfun-cli/wallet.enc`, and the config in `~/.config/pumpfun-cli/config.toml`. A command-line flag overrides an environment variable, which overrides the config file:

| Variable | Purpose |
|---|---|
| `PUMPFUN_RPC` | HTTPS RPC endpoint (or `--rpc`) |
| `PUMPFUN_KEYFILE` | Path to the encrypted wallet (or `--keyfile`) |
| `PUMPFUN_PASSWORD` | Wallet password, so commands don't prompt for it |
| `PUMPFUN_PRIORITY_FEE` | Priority fee in micro-lamports (or `--priority-fee`) |
| `PUMPFUN_COMPUTE_UNITS` | Compute unit limit (or `--compute-units`) |

### 4. Trade

```bash
pumpfun info <mint>                 # where it trades, price, quote asset
pumpfun buy <mint> 0.1 --dry-run    # preview: nothing is sent
pumpfun buy <mint> 0.1 --confirm    # spend exactly 0.1 of the coin's quote asset
pumpfun sell <mint> all --confirm
pumpfun tx-status <signature>       # did it land?
```

`--json` makes any command answer in JSON; it is on automatically when the output is piped.

### 5. Launch a coin

```bash
pumpfun launch --name "MyToken" --ticker "MTK" --uri https://example.com/mytoken.json --buy 0.1
```

pump.fun no longer accepts anonymous metadata uploads, so `launch` takes the URI of a metadata JSON you host (`name`, `symbol`, `description`, `image`). Without `--uri` it still tries the upload and says so when it is refused. `--buy` buys in the same transaction as the create, so nobody buys first.

## Commands

```
Token info (requires RPC):
  pumpfun info <mint>                     Venue, price, bonding progress, reserves

Trading (requires RPC + wallet):
  pumpfun buy <mint> <amount> [--slippage N] [--force-amm] [--dry-run] [--confirm]
  pumpfun sell <mint> <amount|all> [--slippage N] [--force-amm] [--dry-run] [--confirm]
  pumpfun migrate <mint> [--confirm]
  pumpfun claim-cashback [--quote-mint M] [--confirm]
  pumpfun collect-creator-fee [--quote-mint M] [--confirm]
  pumpfun close-volume-acc [--confirm]

Transaction inspection (requires RPC):
  pumpfun tx-status <signature>           Confirmation status, slot, fee, errors

Token launch (requires RPC + wallet):
  pumpfun launch --name X --ticker Y [--uri U | --desc D --image P] [--buy N]
                 [--quote-mint M] [--creator-fee-bps N] [--holder-reward]
                 [--mayhem] [--slippage N] [--confirm]

Token discovery (price and progress added when an RPC is set):
  pumpfun tokens trending [--limit N]     pump.fun's movers board
  pumpfun tokens new [--limit N]          Recently launched
  pumpfun tokens graduating [--limit N]   Closest to bonding curve completion
  pumpfun tokens recommended [--limit N]  Recommended by pump.fun (at most 10)
  pumpfun tokens search <query>           Search by name or ticker

Wallet management:
  pumpfun wallet create                   Generate + encrypt keypair
  pumpfun wallet import <keypair.json>    Import existing keypair
  pumpfun wallet show                     Display public key
  pumpfun wallet balance                  SOL + token balances
  pumpfun wallet tokens                   Token accounts with balances
  pumpfun wallet transfer <to> <amount>   Transfer SOL or tokens (--mint for SPL)
  pumpfun wallet close-atas               Close empty token accounts, recover rent
  pumpfun wallet drain <recipient>        Close all ATAs + transfer remaining SOL
  pumpfun wallet export --output <path>   Export as Solana keypair JSON

Config:
  pumpfun config set <key> <value>
  pumpfun config get <key>
  pumpfun config list
  pumpfun config delete <key>

Global options:
  --version           Show version and exit
  --json              Machine-readable JSON output
  --rpc <url>         Override RPC endpoint
  --keyfile           Override wallet keystore path
  --priority-fee N    Priority fee in micro-lamports (overrides default)
  --compute-units N   Compute unit limit (overrides default)
```

## Trading reference

### Venues

`buy`, `sell` and `info` find where a coin trades and go there; `venue` in every result says which:

| Coin | On its curve | After graduation |
|---|---|---|
| pump.fun | `bonding_curve` | `pumpswap` (PumpSwap) |
| Raydium LaunchLab: letsbonk.fun, StonkFun, other launchpads | `launchlab` | `cpmm` (Raydium CPMM) |

A mint with no pump.fun bonding curve is looked up on LaunchLab, and LaunchLab results name the launchpad (`platform`). `--force-amm` skips the curve and trades in the coin's pool: PumpSwap, or CPMM for a LaunchLab coin. A LaunchLab coin that graduated to Raydium AMM v4 instead is refused. `launch`, `migrate`, the fee and cashback commands and `tokens` are pump.fun only.

### Quote assets

Amounts are in the coin's quote asset. Most pump.fun coins are priced in SOL, but a coin can be priced in USDC or another admitted mint, and LaunchLab coins often are (tokenized stocks, other tokens). `buy`, `sell` and `info` read the quote asset from the coin and label their output with it (`quote_symbol`). Buying such a coin spends that asset, so the wallet has to hold it.

A LaunchLab coin priced in anything but SOL is found with `getProgramAccounts`, so it needs an RPC that serves it.

### Transfer fees

Some LaunchLab coins (StonkFun reward coins, for example) are Token-2022 mints with a transfer fee, shown as `transfer_fee_bps` by `info`. A buy delivers that much less and a sell sends that much less into the pool. The CLI's amounts and slippage floors already count it.

### Amounts in JSON output

An exact amount comes twice: in whole units for reading (`tokens_sold`) and as the integer in raw units (`tokens_sold_raw`). Use the `_raw` field for anything that has to add up; the float can drop a unit. An amount known only as an estimate has no `_raw` twin: `quote_received`, the `collect-creator-fee` totals, and `tokens_received` unless the buy ran with `--confirm`, in which case it is read from the confirmed transaction. If that transaction cannot be read back, a confirmed buy also reports the estimate without `tokens_received_raw`, so check for the field. Dry-run fields (`expected_tokens_raw`, `expected_quote_raw`, `min_*_out_raw`) are exact integers of the quote the transaction would be built from, not executed amounts.

An error comes back as `{"error": <message>, "hint": ..., "exit_code": ...}` with a non-zero exit status.

### Curve limits

A pump.fun bonding curve pays a sell out of its real reserves, which on some coins hold less than the price promises. `sell` then sells the most the curve can pay for and reports the rest as `tokens_kept`; when it can pay nothing it sends nothing and says so. A buy bigger than what is left on the curve fails with a message naming how many tokens remain.

## Endpoints

| Command | Endpoint | Protocol |
|---------|----------|----------|
| `info` | Solana RPC (`getAccountInfo` for bonding curve PDA; LaunchLab: `getMultipleAccounts`, `getProgramAccounts`) | JSON-RPC |
| `buy` | Solana RPC (`getAccountInfo`, `getLatestBlockhash`, `sendTransaction`; LaunchLab adds `getMultipleAccounts`, `getProgramAccounts`) | JSON-RPC |
| `sell` | Solana RPC (`getAccountInfo`, `getTokenAccountBalance`, `getLatestBlockhash`, `sendTransaction`; LaunchLab as `buy`) | JSON-RPC |
| `launch` | Solana RPC (`sendTransaction`); `pump.fun/api/ipfs` only without `--uri` | JSON-RPC (+ HTTPS) |
| `tx-status` | Solana RPC (`getTransaction`) | JSON-RPC |
| `migrate` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `claim-cashback` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `collect-creator-fee` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `close-volume-acc` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `tokens trending` | `frontend-api-v3.pump.fun/coins/boards/movers` | HTTPS |
| `tokens new` | `frontend-api-v3.pump.fun/coins/boards/new` | HTTPS |
| `tokens graduating` | `frontend-api-v3.pump.fun/coins/boards/graduating` | HTTPS |
| `tokens recommended` | `frontend-api-v3.pump.fun/coins/recommendations` | HTTPS |
| `tokens search` | `frontend-api-v3.pump.fun/coins/search-unrestricted` | HTTPS |
| `tokens *` with an RPC set | + Solana RPC (`getMultipleAccounts` for the bonding curves) | JSON-RPC |
| `wallet balance` | Solana RPC (`getBalance`, `getTokenAccountsByOwner`) | JSON-RPC |
| `wallet transfer` | Solana RPC (`sendTransaction`) | JSON-RPC |
| `wallet drain` | Solana RPC (`getTokenAccountsByOwner`, `sendTransaction`) | JSON-RPC |
| `wallet create/show/import/export` | None (local keystore only) | — |
| `config *` | None (local config file only) | — |

The `tokens` listings use pump.fun's frontend API, which is unofficial and changes without notice; it currently refuses non-browser clients ([#33](https://github.com/chainstacklabs/pumpfun-cli/issues/33)). Listings are narrowed to pump.fun coins on Solana, and price and bonding progress come from the chain, so they need an RPC endpoint.

## Throughput and rate limits

Every node provider has its own limits — method availability, requests per second, plan-specific caps. Consult your provider's docs, and don't expect public RPC nodes to hold up. For Chainstack, see the [throughput guidelines](https://docs.chainstack.com/docs/limits).

LaunchLab coins priced in anything but SOL are found with `getProgramAccounts`, filtered by the coin's mint; providers that don't serve that method can't trade them.

For faster execution, Chainstack offers [Solana Trader nodes](https://docs.chainstack.com/docs/solana-trader-nodes) for transaction propagation.

## Security

- Private keys are encrypted at rest (AES-256-GCM + scrypt)
- Password required for any key operation
- Keys never appear in stdout, stderr, or logs
- `wallet export` requires an explicit `--output` flag

## Testing

Unit tests need nothing external:

```bash
uv run pytest
```

For transactions against real program state, the integration tests use [Surfpool](https://www.surfpool.run/), a local Solana fork that loads accounts from mainnet on demand. They are optional and skipped by default:

```bash
./scripts/surfpool-test.sh --mint <ACTIVE_BONDING_CURVE_MINT>                 # starts and stops surfpool
./scripts/surfpool-test.sh --mint <ACTIVE_MINT> --graduated <GRADUATED_MINT>  # graduated coins too
./scripts/surfpool-test.sh --running --mint <MINT>                            # surfpool already running
```

## IDLs

The pump.fun IDLs under [`idl/`](idl/) match those in [pumpfun-bonkfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot), and `raydium_launchlab_idl.json` is copied from it; keep them in sync when the programs change. The IDLs under-report a few account lists (PumpSwap's swaps, pump.fun's `migrate_v2`); [CLAUDE.md](CLAUDE.md) lists what they leave out.

## Architecture

```
commands/  →  core/  →  protocol/
  (thin)      (logic)    (Solana)
```

- **`commands/`** — Typer CLI wiring: parses arguments, calls core, renders output
- **`core/`** — framework-free business logic
- **`protocol/`** — Solana primitives: PDAs, instructions, account layouts, curve math

## Agentic coding

This repo is configured for AI coding agents via the `.claude/` directory:

- **`CLAUDE.md`** — project context, commands, conventions and boundaries. `AGENTS.md` is a symlink to it, so Claude Code, Codex, Cursor and Copilot read the same guide.
- **`hooks/`** — auto-lint on edit, guard against writing secrets, warn on transaction commands
- **`skills/`** — [Agent Skills](https://agentskills.io/home) for repeatable workflows:

| Skill | Purpose |
|-------|---------|
| `run-unit-and-surfpool-tests` | Run unit tests + optional Surfpool integration tests |
| `run-mainnet-e2e-tests` | Run end-to-end tests against Solana mainnet (costs real SOL) |
| `work-item` | Investigate, plan, implement (TDD), verify, and finalize work items as PRs |

## Contributing

Open an **Issue** for feedback or bugs. [CONTRIBUTING.md](CONTRIBUTING.md) covers setup, architecture and how to submit changes.
