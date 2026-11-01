"""Token discovery commands."""

import asyncio

import typer

from pumpfun_cli.core.tokens import (
    TokenApiError,
    enrich_from_chain,
    get_graduating_tokens,
    get_new_tokens,
    get_recommended_tokens,
    get_trending_tokens,
    search_tokens,
)
from pumpfun_cli.group import JsonAwareGroup
from pumpfun_cli.output import error, render, render_table

app = typer.Typer(
    help="Browse and search pump.fun tokens.", invoke_without_command=True, cls=JsonAwareGroup
)


@app.callback()
def _tokens_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(0)


TOKEN_COLUMNS = [
    ("name", "Name"),
    ("symbol", "Ticker"),
    ("_price", "Price"),
    ("_progress", "Progress"),
    ("_mcap", "MCap"),
    ("mint", "Mint"),
]


def _fmt_mcap(mcap) -> str:
    if not mcap:
        return ""
    if mcap >= 1_000_000:
        return f"${mcap / 1_000_000:.1f}M"
    if mcap >= 1_000:
        return f"${mcap / 1_000:.1f}K"
    return f"${mcap:.0f}"


def _list(ctx: typer.Context, fetch) -> None:
    """Fetch a listing, add chain data when an RPC is configured, and render it."""
    state = ctx.obj
    rpc = state.rpc if state else None

    enrich_failed = False

    async def run():
        nonlocal enrich_failed
        tokens = await fetch
        if rpc:
            try:
                tokens = await enrich_from_chain(tokens, rpc)
            except (RuntimeError, ValueError):
                enrich_failed = True  # the listing is still useful without chain data
        return tokens

    try:
        tokens = asyncio.run(run())
    except TokenApiError as exc:
        error(str(exc), hint="pump.fun's frontend API is unofficial and changes without notice.")
    if render(tokens, state and state.json_mode):
        return
    if enrich_failed:
        typer.echo("Could not read prices from chain; showing pump.fun's data only.", err=True)
    for t in tokens:
        price = t.get("price")
        symbol = t.get("quote_symbol") or ""
        if len(symbol) > 6:
            symbol = f"{symbol[:4]}\u2026"
        t["_price"] = f"{price:.4g} {symbol}" if price is not None else "\u2014"
        progress = t.get("bonding_progress")
        t["_progress"] = f"{progress}%" if progress is not None else "\u2014"
        t["_mcap"] = _fmt_mcap(t.get("usd_market_cap"))
    render_table(tokens, TOKEN_COLUMNS)


@app.command("trending")
def trending(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Coins moving most right now (pump.fun's movers board)."""
    _list(ctx, get_trending_tokens(limit=limit))


@app.command("new")
def new(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Recently launched tokens."""
    _list(ctx, get_new_tokens(limit=limit))


@app.command("graduating")
def graduating(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Tokens near bonding curve completion."""
    _list(ctx, get_graduating_tokens(limit=limit))


@app.command("recommended")
@app.command("top", hidden=True)
def recommended(ctx: typer.Context, limit: int = typer.Option(10, "--limit", "-n", min=1)):
    """Recommended tokens by pump.fun (at most 10)."""
    _list(ctx, get_recommended_tokens(limit=limit))


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", "-n", min=1),
):
    """Search tokens by name or ticker."""
    _list(ctx, search_tokens(query, limit=limit))
