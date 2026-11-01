"""Token info command."""

import asyncio

import typer

from pumpfun_cli.core.info import get_token_info
from pumpfun_cli.output import error, render


def info(
    ctx: typer.Context,
    mint: str = typer.Argument(..., help="Token mint address"),
    rpc_timeout: float = typer.Option(30.0, "--timeout", help="RPC timeout in seconds"),
):
    """Display on-chain token info — price, bonding progress, reserves."""
    try:
        from solders.pubkey import Pubkey as _Pk

        _Pk.from_string(mint)
    except ValueError:
        error("Invalid mint address.", hint="Provide a valid base58 Solana address.")
    state = ctx.obj
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")
    try:
        result = asyncio.run(get_token_info(state.rpc, mint, rpc_timeout=rpc_timeout))
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    if not render(result, state.json_mode):
        typer.echo(f"Mint:             {result['mint']}")
        symbol = result["quote_symbol"]
        typer.echo(f"Price:            {result['price']:.10f} {symbol}")
        typer.echo(f"Bonding progress: {result['bonding_progress']}%")
        typer.echo(f"Graduated:        {result['graduated']}")
        if result["graduated"] and result.get("pool_address"):
            typer.echo(f"Pool:             {result['pool_address']}")
            typer.echo(f"Base reserves:    {result['base_reserves']:.2f}")
            typer.echo(f"Quote reserves:   {result['quote_reserves']:.4f} {symbol}")
        else:
            typer.echo(f"Quote reserves:   {result['real_quote_reserves']:.4f} {symbol}")
        if result.get("pumpswap_warning"):
            typer.echo(f"Warning:          {result['pumpswap_warning']}")
        typer.echo(f"Creator:          {result['creator']}")
        if result["is_mayhem_mode"]:
            typer.echo("Mayhem mode:      Yes")
        if result["is_cashback_coin"]:
            typer.echo("Cashback:         Yes")
        if result.get("is_holder_reward"):
            typer.echo("Holder rewards:   Yes")
        if result.get("creator_fee_bps"):
            typer.echo(f"Creator fee:      {result['creator_fee_bps']} bps")
