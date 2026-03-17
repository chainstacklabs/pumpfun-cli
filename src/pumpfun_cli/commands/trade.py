"""Buy and sell commands."""

import asyncio

import typer

from pumpfun_cli.core.pumpswap import buy_pumpswap, sell_pumpswap
from pumpfun_cli.core.trade import (
    buy_token,
    migrate_token,
    sell_token,
)
from pumpfun_cli.core.trade import (
    claim_cashback as claim_cashback_core,
)
from pumpfun_cli.core.trade import (
    close_volume_accumulator as close_volume_acc_core,
)
from pumpfun_cli.core.trade import (
    collect_creator_fees as collect_creator_fees_core,
)
from pumpfun_cli.output import error, render


def _get_overrides(ctx: typer.Context) -> dict:
    """Extract priority_fee and compute_units from global state."""
    state = ctx.obj
    overrides = {}
    if state and state.priority_fee is not None:
        overrides["priority_fee"] = state.priority_fee
    if state and state.compute_units is not None:
        overrides["compute_units"] = state.compute_units
    return overrides


def _validate_mint(mint: str):
    """Validate mint is a valid base58 pubkey, or exit with error."""
    try:
        from solders.pubkey import Pubkey

        Pubkey.from_string(mint)
    except ValueError:
        error("Invalid mint address.", hint="Provide a valid base58 Solana address.")


def _validate_slippage(slippage: int) -> None:
    """Validate slippage is between 0 and 100, or exit with error."""
    if slippage < 0 or slippage > 100:
        error("Slippage must be between 0 and 100.", hint=f"Got: {slippage}")


def _require_rpc_and_wallet(ctx: typer.Context) -> tuple:
    """Return (rpc, keyfile, password) or exit with error."""
    state = ctx.obj
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")
    from pathlib import Path

    from pumpfun_cli.commands.wallet import _get_keystore_path, _get_password

    keyfile = _get_keystore_path(ctx)
    if not Path(keyfile).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    password = _get_password(ctx)
    return state.rpc, keyfile, password


def buy(
    ctx: typer.Context,
    mint: str = typer.Argument(..., help="Token mint address"),
    sol_amount: float = typer.Argument(..., help="Amount of SOL to spend"),
    slippage: int = typer.Option(
        15, "--slippage", help="Slippage tolerance percent (default: 15)"
    ),
    force_amm: bool = typer.Option(
        False, "--force-amm", help="Skip bonding curve, buy directly on PumpSwap AMM"
    ),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate trade without sending transaction"
    ),
):
    """Buy tokens with SOL."""
    _validate_mint(mint)
    _validate_slippage(slippage)
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        if force_amm:
            result = asyncio.run(
                buy_pumpswap(
                    rpc,
                    keyfile,
                    password,
                    mint,
                    sol_amount,
                    slippage,
                    confirm=confirm,
                    dry_run=dry_run,
                    **overrides,
                )
            )
        else:
            result = asyncio.run(
                buy_token(
                    rpc,
                    keyfile,
                    password,
                    mint,
                    sol_amount,
                    slippage,
                    confirm=confirm,
                    dry_run=dry_run,
                    **overrides,
                )
            )
            if result.get("error") == "graduated":
                result = asyncio.run(
                    buy_pumpswap(
                        rpc,
                        keyfile,
                        password,
                        mint,
                        sol_amount,
                        slippage,
                        confirm=confirm,
                        dry_run=dry_run,
                        **overrides,
                    )
                )
    except ValueError as exc:
        error(str(exc))
    if result.get("dry_run"):
        state = ctx.obj
        if not render(result, state.json_mode):
            typer.echo("Dry run — no transaction sent\n")
            typer.echo(f"  Action:          {result['action']}")
            typer.echo(f"  Venue:           {result['venue']}")
            typer.echo(f"  SOL in:          {result['sol_in']}")
            typer.echo(f"  Expected tokens: {result['expected_tokens']:.6f}")
            typer.echo(f"  Effective price: {result['effective_price_sol']:.10f} SOL/token")
            typer.echo(f"  Spot price:      {result['spot_price_sol']:.10f} SOL/token")
            typer.echo(f"  Price impact:    {result['price_impact_pct']:.2f}%")
            typer.echo(
                f"  Min tokens out:  {result['min_tokens_out']:.6f} ({result['slippage_pct']}% slippage)"
            )
        return
    if result.get("error"):
        code = 3 if result["error"] in ("graduated", "slippage") else 1
        error(result["message"], exit_code=code)
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(f"Bought {result['tokens_received']:.2f} tokens for {result['sol_spent']} SOL")
        typer.echo(f"TX: {result['explorer']}")


def sell(
    ctx: typer.Context,
    mint: str = typer.Argument(..., help="Token mint address"),
    amount: str = typer.Argument(..., help="Token amount to sell, or 'all'"),
    slippage: int = typer.Option(
        15, "--slippage", help="Slippage tolerance percent (default: 15)"
    ),
    force_amm: bool = typer.Option(
        False, "--force-amm", help="Skip bonding curve, sell directly on PumpSwap AMM"
    ),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate trade without sending transaction"
    ),
):
    """Sell tokens for SOL."""
    _validate_mint(mint)
    _validate_slippage(slippage)
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        if force_amm:
            result = asyncio.run(
                sell_pumpswap(
                    rpc,
                    keyfile,
                    password,
                    mint,
                    amount,
                    slippage,
                    confirm=confirm,
                    dry_run=dry_run,
                    **overrides,
                )
            )
        else:
            result = asyncio.run(
                sell_token(
                    rpc,
                    keyfile,
                    password,
                    mint,
                    amount,
                    slippage,
                    confirm=confirm,
                    dry_run=dry_run,
                    **overrides,
                )
            )
            if result.get("error") == "graduated":
                result = asyncio.run(
                    sell_pumpswap(
                        rpc,
                        keyfile,
                        password,
                        mint,
                        amount,
                        slippage,
                        confirm=confirm,
                        dry_run=dry_run,
                        **overrides,
                    )
                )
    except ValueError as exc:
        error(str(exc))
    if result.get("dry_run"):
        state = ctx.obj
        if not render(result, state.json_mode):
            typer.echo("Dry run — no transaction sent\n")
            typer.echo(f"  Action:          {result['action']}")
            typer.echo(f"  Venue:           {result['venue']}")
            typer.echo(f"  Tokens in:       {result['tokens_in']:.6f}")
            typer.echo(f"  Expected SOL:    {result['expected_sol']:.6f}")
            typer.echo(f"  Effective price: {result['effective_price_sol']:.10f} SOL/token")
            typer.echo(f"  Spot price:      {result['spot_price_sol']:.10f} SOL/token")
            typer.echo(f"  Price impact:    {result['price_impact_pct']:.2f}%")
            typer.echo(
                f"  Min SOL out:     {result['min_sol_out']:.6f} ({result['slippage_pct']}% slippage)"
            )
        return
    if result.get("error"):
        code = 3 if result["error"] in ("graduated", "slippage", "no_tokens") else 1
        error(result["message"], exit_code=code)
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(f"Sold {result['tokens_sold']:.2f} tokens for {result['sol_received']:.4f} SOL")
        typer.echo(f"TX: {result['explorer']}")


def claim_cashback(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Claim volume-based cashback rewards."""
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            claim_cashback_core(rpc, keyfile, password, confirm=confirm, **overrides)
        )
    except ValueError as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo("Cashback claimed!")
        typer.echo(f"TX: {result['explorer']}")


def close_volume_acc(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Close volume accumulator account, recover rent."""
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            close_volume_acc_core(rpc, keyfile, password, confirm=confirm, **overrides)
        )
    except ValueError as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo("Volume accumulator closed, rent recovered.")
        typer.echo(f"TX: {result['explorer']}")


def migrate(
    ctx: typer.Context,
    mint: str = typer.Argument(..., help="Token mint address"),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Trigger migration from bonding curve to PumpSwap AMM."""
    _validate_mint(mint)
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            migrate_token(rpc, keyfile, password, mint, confirm=confirm, **overrides)
        )
    except ValueError as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(f"Migrated {result['mint']} to PumpSwap!")
        typer.echo(f"TX: {result['explorer']}")


def collect_creator_fee(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Collect creator fees from pump.fun and PumpSwap vaults."""
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            collect_creator_fees_core(rpc, keyfile, password, confirm=confirm, **overrides)
        )
    except ValueError as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(f"Pump.fun fees: {result['pump_recovered_sol']:.6f} SOL")
        typer.echo(f"PumpSwap fees: {result['pumpswap_recovered_sol']:.6f} SOL")
        typer.echo(f"TX: {result['explorer']}")
