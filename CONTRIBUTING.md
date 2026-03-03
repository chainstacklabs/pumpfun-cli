# Contributing

## Setup

Install [uv](https://docs.astral.sh/uv/) (it handles Python automatically), then:

```bash
git clone https://github.com/chainstacklabs/pumpfun-cli.git
cd pumpfun-cli
uv sync --dev
uv run pre-commit install
uv run pytest tests/ -q
```

This installs dependencies, sets up git hooks (ruff runs automatically on each commit), and verifies tests pass.

## Architecture

```
commands/  →  core/  →  protocol/
  (thin)      (logic)    (Solana)
```

- **`commands/`** — CLI wiring (Typer). Parses args, calls core, renders output.
- **`core/`** — Business logic. Takes primitives, returns `dict`. No framework imports.
- **`protocol/`** — Solana/pump.fun primitives. PDAs, instructions, curve math. No business logic.

Rule: `commands/` never imports from `protocol/`. Always go through `core/`.

## Tests

```bash
uv run pytest tests/ -q              # all unit tests
uv run pytest tests/test_core -v     # one module
uv run pytest tests/ -k test_buy     # by name
uv run pytest tests/ -v --cov        # with coverage
```

Surfpool integration tests (`tests/test_surfpool/`) are skipped by default. See README for setup.

## Code Style

Ruff handles formatting and linting:

```bash
uv run ruff format src/ tests/
uv run ruff check --fix src/ tests/
```

CI rejects PRs that fail these checks.

Conventions:
- `render(data, json_mode)` for output, `error(msg)` for failures — no `print()`
- I/O functions are `async def`, called via `asyncio.run()` in commands
- Import order: stdlib → third-party → local (ruff enforces this)
- Type hints on public functions

## Adding a Command

1. `src/pumpfun_cli/core/my_feature.py` — async logic, returns `dict`
2. `src/pumpfun_cli/commands/my_feature.py` — Typer wrapper, calls core
3. Register in `cli.py`
4. `tests/test_core/test_my_feature.py` — tests with mocked RPC

Look at `commands/wallet.py` + `core/wallet.py` for a real example.

## Pull Requests

1. Branch from `main`
2. Make changes
3. `uv run pytest tests/ -q && uv run ruff check src/ tests/`
4. Push and open a PR

PR titles must use [conventional commits](https://www.conventionalcommits.org/):

```
feat: add token transfer command
fix: handle graduated token slippage
chore: update ruff to 0.16
docs: add migration guide
test: add curve math edge cases
```

PRs are squash-merged — the PR title becomes the commit message on `main`.

Changes to `protocol/` (transaction construction, instructions, PDAs) — say so in the PR. Bugs there can lose funds.

## Issues

Look for [`good first issue`](https://github.com/chainstacklabs/pumpfun-cli/labels/good%20first%20issue) to get started. Issues are tagged by area: `protocol`, `wallet`, `pumpswap`, `bonding-curve`, `cli`, `devex`.
