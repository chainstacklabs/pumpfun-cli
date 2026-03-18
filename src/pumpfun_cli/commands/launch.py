"""Token launch command."""

import asyncio

import typer

from pumpfun_cli.core.launch import launch_token
from pumpfun_cli.output import error, render


def launch(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Token name"),
    ticker: str = typer.Option(..., "--ticker", help="Token ticker/symbol"),
    desc: str = typer.Option(..., "--desc", help="Token description"),
    image: str | None = typer.Option(None, "--image", help="Path to token image"),
    buy: float | None = typer.Option(None, "--buy", help="Initial buy amount in SOL"),
    mayhem: bool = typer.Option(False, "--mayhem", help="Enable mayhem mode"),
    cashback: bool = typer.Option(False, "--cashback", help="Enable cashback for the token"),
):
    """Launch a new token on pump.fun (create_v2 + extend_account)."""
    state = ctx.obj
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")

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
                desc,
                image,
                buy,
                mayhem,
                cashback,
                **overrides,
            )
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    if not render(result, state.json_mode):
        typer.echo("Token launched!")
        typer.echo(f"  Name:     {result['name']}")
        typer.echo(f"  Ticker:   {result['ticker']}")
        typer.echo(f"  Mint:     {result['mint']}")
        typer.echo(f"  TX:       {result['explorer']}")
        typer.echo(f"  Pump.fun: {result['pump_url']}")
        if result.get("is_cashback"):
            typer.echo("  Cashback: enabled")
        if result.get("initial_buy_sol"):
            typer.echo(f"  Buy:      {result['initial_buy_sol']} SOL")
