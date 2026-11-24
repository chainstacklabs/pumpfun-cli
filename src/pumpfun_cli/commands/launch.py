"""Token launch command."""

import asyncio

import typer

from pumpfun_cli.commands.sending import confirm_option, fast_option, outcome, wait_for_outcome
from pumpfun_cli.core.launch import launch_token
from pumpfun_cli.output import error, render


def launch(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Token name"),
    ticker: str = typer.Option(..., "--ticker", help="Token ticker/symbol"),
    uri: str = typer.Option(
        ...,
        "--uri",
        help="URI of the metadata JSON you host (name, symbol, description, image)",
    ),
    buy: float | None = typer.Option(
        None,
        "--buy",
        help="Opening buy, in the quote asset, bought in the same transaction as the create",
    ),
    quote_mint: str | None = typer.Option(
        None,
        "--quote-mint",
        help="Price the coin in this mint instead of SOL (e.g. USDC); the wallet must hold it",
    ),
    creator_fee_bps: int | None = typer.Option(
        None,
        "--creator-fee-bps",
        help="Creator fee in basis points; only applies to coins priced in a QuoteControl mint",
    ),
    holder_reward: bool = typer.Option(
        False, "--holder-reward", help="Pay the creator fee to holders instead of the creator"
    ),
    mayhem: bool = typer.Option(False, "--mayhem", help="Enable mayhem mode (SOL coins only)"),
    slippage: int = typer.Option(
        15, "--slippage", help="Slippage tolerance percent for the opening buy (default: 15)"
    ),
    fast: bool = fast_option(),
    confirm: bool = confirm_option(),
):
    """Launch a new token on pump.fun (create_v2 + extend_account)."""
    confirm = wait_for_outcome(fast, confirm)
    state = ctx.obj
    if not name.strip():
        error("Token name cannot be empty.", exit_code=2)
    if not ticker.strip():
        error("Token ticker cannot be empty.", exit_code=2)
    if not uri.strip():
        error("Metadata URI cannot be empty.", hint="Pass --uri <url>", exit_code=2)
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")
    if slippage < 0 or slippage > 100:
        error("Slippage must be between 0 and 100.", hint=f"Got: {slippage}")
    if creator_fee_bps is not None and creator_fee_bps < 0:
        error("Creator fee cannot be negative.", hint=f"Got: {creator_fee_bps}")
    if buy is not None and buy < 0:
        error("Buy amount cannot be negative.", hint=f"Got: {buy}")

    from pathlib import Path

    from pumpfun_cli.commands.wallet import _get_keystore_path, _get_password

    keyfile = _get_keystore_path(ctx)
    if not Path(keyfile).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    password = _get_password(ctx)

    overrides = {}
    if state.priority_fee is not None:
        overrides["priority_fee"] = state.priority_fee
    if state.compute_units is not None:
        overrides["compute_units"] = state.compute_units

    try:
        result = asyncio.run(
            launch_token(
                state.rpc,
                keyfile,
                password,
                name,
                ticker,
                uri,
                initial_buy=buy,
                is_mayhem=mayhem,
                quote_mint_str=quote_mint,
                creator_fee_bps=creator_fee_bps,
                is_holder_reward=holder_reward,
                slippage=slippage,
                confirm=confirm,
                **overrides,
            )
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    if not render(result, state.json_mode):
        typer.echo(outcome(result, "Token launched."))
        typer.echo(f"  Name:     {result['name']}")
        typer.echo(f"  Ticker:   {result['ticker']}")
        typer.echo(f"  Mint:     {result['mint']}")
        typer.echo(f"  Quote:    {result['quote_symbol']}")
        typer.echo(f"  TX:       {result['explorer']}")
        typer.echo(f"  Pump.fun: {result['pump_url']}")
        if result.get("is_holder_reward"):
            typer.echo("  Holder rewards: enabled")
        if result.get("creator_fee_bps"):
            typer.echo(f"  Creator fee: {result['creator_fee_bps']} bps")
        if result.get("initial_buy"):
            typer.echo(f"  Buy:      {result['initial_buy']} {result['quote_symbol']}")
