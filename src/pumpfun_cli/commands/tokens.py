"""Token discovery commands."""

import asyncio

import typer

from pumpfun_cli.core.tokens import (
    get_graduating_tokens,
    get_new_tokens,
    get_recommended_tokens,
    get_trending_tokens,
    search_tokens,
)
from pumpfun_cli.group import JsonAwareGroup
from pumpfun_cli.output import render, render_table

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
    ("price_sol", "Price (SOL)"),
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


def _display_tokens(ctx: typer.Context, tokens: list[dict]):
    state = ctx.obj
    if render(tokens, state and state.json_mode):
        return
    for t in tokens:
        price = t.get("price_sol")
        t["price_sol"] = f"{price:.8f}" if price is not None else "\u2014"
        progress = t.get("bonding_progress")
        t["_progress"] = f"{progress}%" if progress is not None else "\u2014"
        t["_mcap"] = _fmt_mcap(t.get("usd_market_cap") or t.get("market_cap"))
    render_table(tokens, TOKEN_COLUMNS)


@app.command("trending")
def trending(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Top runners + recommended tokens."""
    tokens = asyncio.run(get_trending_tokens(limit=limit))
    _display_tokens(ctx, tokens)


@app.command("new")
def new(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Recently launched tokens."""
    tokens = asyncio.run(get_new_tokens(limit=limit))
    _display_tokens(ctx, tokens)


@app.command("graduating")
def graduating(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Tokens near bonding curve completion."""
    tokens = asyncio.run(get_graduating_tokens(limit=limit))
    _display_tokens(ctx, tokens)


@app.command("recommended")
def recommended(ctx: typer.Context, limit: int = typer.Option(20, "--limit", "-n", min=1)):
    """Recommended tokens by pump.fun."""
    tokens = asyncio.run(get_recommended_tokens(limit=limit))
    _display_tokens(ctx, tokens)


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", "-n", min=1),
):
    """Search tokens by keyword."""
    tokens = asyncio.run(search_tokens(query, limit=limit))
    _display_tokens(ctx, tokens)
