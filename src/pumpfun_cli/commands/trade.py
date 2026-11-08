"""Buy and sell commands."""

import asyncio

import typer

from pumpfun_cli.core.launchlab import buy_launchlab, sell_launchlab
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


def _route(curve, amm, launchlab, force_amm: bool, mint: str, call) -> dict:
    """Trade where the coin lives: pump.fun's curve, then PumpSwap once it has
    graduated, or a LaunchLab curve when pump.fun has no such coin.

    `call(fn)` runs one venue's core function with the command's arguments.
    """
    if force_amm:
        return call(amm)
    result = call(curve)
    if result.get("error") == "graduated":
        return call(amm)
    if result.get("error") == "not_found":
        result = call(launchlab)
        if result.get("error") == "not_found":
            result["message"] = f"No pump.fun or LaunchLab coin found for {mint}."
    return result


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
    amount: float = typer.Argument(
        ..., help="Amount to spend, in the coin's quote asset (SOL for most coins)"
    ),
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
    """Buy tokens, spending an exact amount of the coin's quote asset."""
    _validate_mint(mint)
    if amount <= 0:
        error("Amount must be greater than 0.", hint=f"Got: {amount}", exit_code=2)
    _validate_slippage(slippage)
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = _route(
            buy_token,
            buy_pumpswap,
            buy_launchlab,
            force_amm,
            mint,
            lambda fn: asyncio.run(
                fn(
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
            ),
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("dry_run"):
        state = ctx.obj
        if not render(result, state.json_mode):
            typer.echo("Dry run — no transaction sent\n")
            typer.echo(f"  Action:          {result['action']}")
            typer.echo(f"  Venue:           {result['venue']}")
            typer.echo(f"  Spend:           {result['quote_in']} {result['quote_symbol']}")
            typer.echo(f"  Expected tokens: {result['expected_tokens']:.6f}")
            unit = f"{result['quote_symbol']}/token"
            typer.echo(f"  Effective price: {result['effective_price']:.10f} {unit}")
            typer.echo(f"  Spot price:      {result['spot_price']:.10f} {unit}")
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
        typer.echo(
            f"Bought {result['tokens_received']:.2f} tokens"
            f" for {result['quote_spent']} {result['quote_symbol']}"
        )
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
    """Sell tokens for the coin's quote asset (SOL for most coins)."""
    _validate_mint(mint)
    _validate_slippage(slippage)
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = _route(
            sell_token,
            sell_pumpswap,
            sell_launchlab,
            force_amm,
            mint,
            lambda fn: asyncio.run(
                fn(
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
            ),
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("dry_run"):
        state = ctx.obj
        if not render(result, state.json_mode):
            typer.echo("Dry run — no transaction sent\n")
            typer.echo(f"  Action:          {result['action']}")
            typer.echo(f"  Venue:           {result['venue']}")
            typer.echo(f"  Tokens in:       {result['tokens_in']:.6f}")
            symbol = result["quote_symbol"]
            typer.echo(f"  Expected out:    {result['expected_quote']:.6f} {symbol}")
            typer.echo(f"  Effective price: {result['effective_price']:.10f} {symbol}/token")
            typer.echo(f"  Spot price:      {result['spot_price']:.10f} {symbol}/token")
            typer.echo(f"  Price impact:    {result['price_impact_pct']:.2f}%")
            typer.echo(
                f"  Min out:         {result['min_quote_out']:.6f} {symbol}"
                f" ({result['slippage_pct']}% slippage)"
            )
            if "tokens_kept" in result:
                typer.echo(f"  Kept:            {result['tokens_kept']:.6f} (curve can't pay)")
        return
    if result.get("error"):
        code = 3 if result["error"] in ("graduated", "slippage", "no_tokens") else 1
        error(result["message"], exit_code=code)
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(
            f"Sold {result['tokens_sold']:.2f} tokens"
            f" for {result['quote_received']:.6f} {result['quote_symbol']}"
        )
        if "tokens_kept" in result:
            typer.echo(
                f"Kept {result['tokens_kept']:.2f} tokens: the bonding curve's real"
                " reserves can't pay for them now."
            )
        typer.echo(f"TX: {result['explorer']}")


_QUOTE_MINT_HELP = "Quote asset mint to act on (default: SOL)"


def claim_cashback(
    ctx: typer.Context,
    quote_mint: str | None = typer.Option(None, "--quote-mint", help=_QUOTE_MINT_HELP),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Claim volume-based cashback rewards in one quote asset."""
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            claim_cashback_core(rpc, keyfile, password, quote_mint, confirm=confirm, **overrides)
        )
    except (ValueError, RuntimeError) as exc:
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
    except (ValueError, RuntimeError) as exc:
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
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        typer.echo(f"Migrated {result['mint']} to PumpSwap!")
        typer.echo(f"TX: {result['explorer']}")


def collect_creator_fee(
    ctx: typer.Context,
    quote_mint: str | None = typer.Option(None, "--quote-mint", help=_QUOTE_MINT_HELP),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Collect creator fees in one quote asset from pump.fun and PumpSwap vaults."""
    rpc, keyfile, password = _require_rpc_and_wallet(ctx)
    overrides = _get_overrides(ctx)
    try:
        result = asyncio.run(
            collect_creator_fees_core(
                rpc, keyfile, password, quote_mint, confirm=confirm, **overrides
            )
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    state = ctx.obj
    if not render(result, state.json_mode):
        symbol = result["quote_symbol"]
        typer.echo(f"Pump.fun fees: {result['pump_recovered']:.6f} {symbol}")
        typer.echo(f"PumpSwap fees: {result['pumpswap_recovered']:.6f} {symbol}")
        typer.echo(f"TX: {result['explorer']}")
