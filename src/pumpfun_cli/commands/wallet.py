"""Wallet management commands."""

import asyncio
import os
import sys
from pathlib import Path

import typer

from pumpfun_cli.core.config import get_config_dir, resolve_value
from pumpfun_cli.core.wallet import (
    close_empty_atas,
    create_wallet,
    drain_wallet,
    export_wallet,
    get_balance,
    import_wallet,
    list_token_accounts,
    show_wallet,
    transfer_all_sol,
    transfer_sol,
    transfer_token,
)
from pumpfun_cli.group import JsonAwareGroup
from pumpfun_cli.output import error, render, render_table

app = typer.Typer(help="Manage wallet keys.", invoke_without_command=True, cls=JsonAwareGroup)


@app.callback()
def _wallet_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(0)


def _default_keystore() -> str:
    return str(get_config_dir() / "wallet.enc")


def _get_password(ctx: typer.Context) -> str:
    pw = os.environ.get("PUMPFUN_PASSWORD")
    if pw:
        return pw
    if not sys.stdin.isatty():
        error("Password required. Use --password-file or PUMPFUN_PASSWORD env var.")
    return typer.prompt("Password", hide_input=True)


def _get_keystore_path(ctx: typer.Context) -> str:
    state = ctx.obj
    path = state.keyfile if state else None
    return path or resolve_value("keyfile") or _default_keystore()


@app.command(
    "create",
    epilog="Password: use --password flag, PUMPFUN_PASSWORD env var, or enter interactively.",
)
def wallet_create(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Overwrite existing wallet file"),
    password: str | None = typer.Option(
        None, "--password", help="Wallet password (or set PUMPFUN_PASSWORD env var)"
    ),
):
    """Generate a new wallet keypair and encrypt it."""
    path = _get_keystore_path(ctx)
    if password is not None:
        pw = password
    else:
        pw = _get_password(ctx)
        # Only prompt for confirmation if password was entered interactively
        if not os.environ.get("PUMPFUN_PASSWORD"):
            confirm_pw = typer.prompt("Confirm password", hide_input=True)
            if pw != confirm_pw:
                error("Passwords do not match.")
    result = create_wallet(pw, path, force=force)
    if result.get("error") == "wallet_exists":
        error(
            result["message"],
            hint=f"Existing wallet address: {result['existing_pubkey']}. Use --force to overwrite.",
        )
    if not render(result, ctx.obj and ctx.obj.json_mode):
        typer.echo(f"Created: {result['path']}")
        typer.echo(f"Public key: {result['pubkey']}")


@app.command(
    "import",
    epilog="Password: use --password flag, PUMPFUN_PASSWORD env var, or enter interactively.",
)
def wallet_import(
    ctx: typer.Context,
    keypair_json: str = typer.Argument(..., help="Path to Solana keypair JSON file"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing wallet file"),
    password: str | None = typer.Option(
        None, "--password", help="Wallet password (or set PUMPFUN_PASSWORD env var)"
    ),
):
    """Import an existing Solana keypair and encrypt it."""
    path = _get_keystore_path(ctx)
    if not Path(keypair_json).exists():
        error(f"File not found: {keypair_json}")
    if password is not None:
        pw = password
    else:
        pw = _get_password(ctx)
        # Only prompt for confirmation if password was entered interactively
        if not os.environ.get("PUMPFUN_PASSWORD"):
            confirm_pw = typer.prompt("Confirm password", hide_input=True)
            if pw != confirm_pw:
                error("Passwords do not match.")
    result = import_wallet(keypair_json, pw, path, force=force)
    if result.get("error") == "wallet_exists":
        error(
            result["message"],
            hint=f"Existing wallet address: {result['existing_pubkey']}. Use --force to overwrite.",
        )
    if not render(result, ctx.obj and ctx.obj.json_mode):
        typer.echo(f"Imported: {result['path']}")
        typer.echo(f"Public key: {result['pubkey']}")


@app.command("show")
def wallet_show(ctx: typer.Context):
    """Display wallet public key (no password needed)."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    result = show_wallet(path)
    if not render(result, ctx.obj and ctx.obj.json_mode):
        typer.echo(f"Public key: {result['pubkey']}")
        typer.echo(f"Keystore:   {result['path']}")


@app.command("export")
def wallet_export(
    ctx: typer.Context,
    output: str = typer.Option(..., "--output", help="Output path for Solana keypair JSON"),
):
    """Export wallet as standard Solana keypair JSON (unencrypted)."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    password = _get_password(ctx)
    try:
        export_wallet(path, password, output)
    except ValueError as exc:
        error(str(exc))
    if not (ctx.obj and ctx.obj.json_mode):
        typer.echo(f"Exported to {output}")
        typer.echo("WARNING: This file contains your unencrypted private key.")
        typer.echo("         Store it securely and delete when done.")


def _require_rpc(ctx: typer.Context) -> str:
    state = ctx.obj
    if not state or not state.rpc:
        error("RPC endpoint not configured.", hint="Run: pumpfun config set rpc <url>")
    return state.rpc


@app.command("balance")
def wallet_balance(ctx: typer.Context):
    """Check SOL balance (no password needed)."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    rpc = _require_rpc(ctx)
    pubkey = show_wallet(path)["pubkey"]
    result = asyncio.run(get_balance(rpc, pubkey))
    if not render(result, ctx.obj and ctx.obj.json_mode):
        typer.echo(f"Balance: {result['sol_balance']:.6f} SOL")


@app.command("tokens")
def wallet_tokens(
    ctx: typer.Context,
    show_empty: bool = typer.Option(
        False, "--show-empty", help="Include zero-balance token accounts"
    ),
):
    """List all token accounts with balances (no password needed)."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    rpc = _require_rpc(ctx)
    pubkey = show_wallet(path)["pubkey"]
    result = asyncio.run(list_token_accounts(rpc, pubkey, show_empty=show_empty))
    accounts = result["token_accounts"]
    if render(
        {"pubkey": result["pubkey"], "token_accounts": accounts}, ctx.obj and ctx.obj.json_mode
    ):
        return
    if not accounts:
        typer.echo("No token accounts found.")
        return
    render_table(
        accounts,
        [
            ("mint", "Mint"),
            ("ui_amount", "Balance"),
            ("program", "Program"),
        ],
    )


@app.command("transfer")
def wallet_transfer(
    ctx: typer.Context,
    recipient: str = typer.Argument(..., help="Recipient public key"),
    amount: str = typer.Argument(..., help="Amount to send (or 'all' to send max)"),
    mint: str = typer.Option(None, "--mint", help="Token mint address (omit for SOL transfer)"),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Transfer SOL or tokens to another wallet."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    rpc = _require_rpc(ctx)
    password = _get_password(ctx)
    overrides = {}
    state = ctx.obj
    if state and state.priority_fee is not None:
        overrides["priority_fee"] = state.priority_fee
    if state and state.compute_units is not None:
        overrides["compute_units"] = state.compute_units

    from pumpfun_cli.core.validate import parse_pubkey

    if parse_pubkey(recipient) is None:
        error(
            f"Invalid recipient address: {recipient}",
            hint="Provide a valid base58 Solana address.",
        )
    if mint and parse_pubkey(mint) is None:
        error(
            f"Invalid mint address: {mint}",
            hint="Provide a valid base58 Solana address.",
        )

    try:
        if mint:
            result = asyncio.run(
                transfer_token(
                    rpc, path, password, recipient, mint, amount, confirm=confirm, **overrides
                )
            )
        else:
            if amount.lower() == "all":
                result = asyncio.run(
                    transfer_all_sol(rpc, path, password, recipient, confirm=confirm, **overrides)
                )
            else:
                result = asyncio.run(
                    transfer_sol(
                        rpc, path, password, recipient, float(amount), confirm=confirm, **overrides
                    )
                )
    except ValueError as exc:
        error(str(exc))
    if result.get("error"):
        error(result["message"])
    if not render(result, ctx.obj and ctx.obj.json_mode):
        if mint:
            typer.echo(f"Sent {result['amount']} tokens to {result['to']}")
        else:
            typer.echo(f"Sent {result['sol_amount']} SOL to {result['to']}")
        typer.echo(f"TX: {result['explorer']}")


@app.command("close-atas")
def wallet_close_atas(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Close empty token accounts and recover rent SOL."""
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint="Run: pumpfun wallet create")
    rpc = _require_rpc(ctx)
    password = _get_password(ctx)
    overrides = {}
    state = ctx.obj
    if state and state.priority_fee is not None:
        overrides["priority_fee"] = state.priority_fee
    if state and state.compute_units is not None:
        overrides["compute_units"] = state.compute_units

    try:
        result = asyncio.run(close_empty_atas(rpc, path, password, confirm=confirm, **overrides))
    except ValueError as exc:
        error(str(exc))
    if not render(result, ctx.obj and ctx.obj.json_mode):
        if result["closed"] == 0:
            typer.echo("No empty token accounts to close.")
        else:
            typer.echo(
                f"Closed {result['closed']} empty account(s), recovered ~{result['recovered_sol']} SOL"
            )
            typer.echo(f"TX: {result['explorer']}")


@app.command("drain")
def wallet_drain(
    ctx: typer.Context,
    recipient: str = typer.Argument(..., help="Recipient address for remaining SOL"),
    confirm: bool = typer.Option(False, "--confirm", help="Wait for transaction confirmation"),
):
    """Close empty ATAs, then transfer all remaining SOL to recipient."""
    state = ctx.obj
    rpc = _require_rpc(ctx)
    path = _get_keystore_path(ctx)
    if not Path(path).exists():
        error("No wallet found.", hint=f"Expected at {path}")
    password = _get_password(ctx)
    json_mode = state.json_mode if state else False

    overrides = {}
    if state and state.priority_fee is not None:
        overrides["priority_fee"] = state.priority_fee
    if state and state.compute_units is not None:
        overrides["compute_units"] = state.compute_units

    try:
        result = asyncio.run(
            drain_wallet(rpc, path, password, recipient, confirm=confirm, **overrides)
        )
    except ValueError:
        error("Wrong wallet password.")

    if result.get("error"):
        error(result["message"])

    # Render JSON mode
    if render(result, json_mode):
        return

    # TTY output
    if result["non_empty_token_accounts"]:
        typer.echo(
            f"WARNING: {len(result['non_empty_token_accounts'])} non-empty token account(s)"
            " — sell or transfer first:"
        )
        for t in result["non_empty_token_accounts"]:
            typer.echo(f"  {t['mint']}: {t['amount']} tokens")

    if result.get("ata_error"):
        typer.echo(f"ATA close failed: {result['ata_error']}")
    elif result["atas_closed"] > 0:
        typer.echo(
            f"Closed {result['atas_closed']} empty ATA(s),"
            f" recovered ~{result['ata_rent_recovered_sol']} SOL"
        )
    else:
        typer.echo("No empty ATAs to close.")

    if result.get("sol_error"):
        typer.echo(f"SOL transfer skipped: {result['sol_error']}")
    elif result.get("sol_signature"):
        typer.echo(f"Transferred {result['sol_transferred']} SOL to {result['recipient']}")
        typer.echo(f"TX: https://solscan.io/tx/{result['sol_signature']}")
