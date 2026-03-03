"""Transaction status command."""

import asyncio

import typer

from pumpfun_cli.core.tx_status import get_tx_status
from pumpfun_cli.output import error, render


def tx_status(
    ctx: typer.Context,
    signature: str = typer.Argument(..., help="Transaction signature (base58)"),
):
    """Check transaction confirmation status, slot, fee, and errors."""
    state = ctx.obj
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")

    result = asyncio.run(get_tx_status(state.rpc, signature))

    if result.get("error") == "invalid_signature" or result.get("error") == "not_found":
        error(result["message"])

    if not render(result, state.json_mode):
        typer.echo(f"Signature: {result['signature']}")
        typer.echo(f"Status:    {result['status']}")
        typer.echo(f"Slot:      {result['slot']}")
        if result.get("block_time"):
            typer.echo(f"Block time: {result['block_time']}")
        typer.echo(f"Fee:       {result['fee_lamports']} lamports ({result['fee_sol']:.9f} SOL)")
        typer.echo(f"Explorer:  {result['explorer']}")
        if result.get("error"):
            typer.echo(f"Error:     {result['error']}")
