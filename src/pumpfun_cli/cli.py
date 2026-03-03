"""Root CLI application."""

import typer

from pumpfun_cli.core.config import resolve_value
from pumpfun_cli.group import JsonAwareGroup
from pumpfun_cli.output import set_json_mode

app = typer.Typer(
    name="pumpfun",
    help="CLI for pump.fun on Solana — trade, launch, and browse tokens.",
    cls=JsonAwareGroup,
)


class GlobalState:
    json_mode: bool = False
    rpc: str | None = None
    keyfile: str | None = None
    priority_fee: int | None = None
    compute_units: int | None = None


def _version_callback(value: bool):
    if value:
        from importlib.metadata import version

        typer.echo(f"pumpfun-cli {version('pumpfun-cli')}")
        raise SystemExit(0)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    version: bool = typer.Option(
        False, "--version", help="Show version and exit", callback=_version_callback, is_eager=True
    ),
    rpc: str | None = typer.Option(None, "--rpc", help="Solana RPC endpoint URL"),
    keyfile: str | None = typer.Option(
        None, "--keyfile", help="Path to encrypted wallet keystore"
    ),
    priority_fee: int | None = typer.Option(
        None, "--priority-fee", help="Priority fee in micro-lamports (overrides default)"
    ),
    compute_units: int | None = typer.Option(
        None, "--compute-units", help="Compute unit limit (overrides default)"
    ),
):
    """CLI for pump.fun on Solana — trade, launch, and browse tokens."""
    from pumpfun_cli.output import error

    state = GlobalState()
    state.json_mode = json_output or ctx.meta.get("json_override", False)
    set_json_mode(state.json_mode)
    state.rpc = resolve_value("rpc", flag=rpc)
    state.keyfile = resolve_value("keyfile", flag=keyfile)

    pf_raw = resolve_value(
        "priority_fee", flag=str(priority_fee) if priority_fee is not None else None
    )
    if pf_raw is not None:
        try:
            pf_val = int(pf_raw)
        except ValueError:
            error(
                f"Invalid priority fee: {pf_raw}",
                hint="Must be a non-negative integer (micro-lamports).",
            )
        if pf_val < 0:
            error(
                f"Invalid priority fee: {pf_val}",
                hint="Must be a non-negative integer.",
            )
        state.priority_fee = pf_val

    cu_raw = resolve_value(
        "compute_units", flag=str(compute_units) if compute_units is not None else None
    )
    if cu_raw is not None:
        try:
            cu_val = int(cu_raw)
        except ValueError:
            error(
                f"Invalid compute units: {cu_raw}",
                hint="Must be a non-negative integer.",
            )
        if cu_val < 0:
            error(
                f"Invalid compute units: {cu_val}",
                hint="Must be a non-negative integer.",
            )
        state.compute_units = cu_val

    ctx.obj = state
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(0)


from pumpfun_cli.commands.config import app as config_app
from pumpfun_cli.commands.tokens import app as tokens_app
from pumpfun_cli.commands.wallet import app as wallet_app

app.add_typer(config_app, name="config")
app.add_typer(tokens_app, name="tokens")
app.add_typer(wallet_app, name="wallet")

from pumpfun_cli.commands.info import info as info_cmd

app.command("info")(info_cmd)

from pumpfun_cli.commands.launch import launch as launch_cmd

app.command("launch")(launch_cmd)

from pumpfun_cli.commands.trade import (
    buy as buy_cmd,
)
from pumpfun_cli.commands.trade import (
    claim_cashback as claim_cashback_cmd,
)
from pumpfun_cli.commands.trade import (
    close_volume_acc as close_volume_acc_cmd,
)
from pumpfun_cli.commands.trade import (
    collect_creator_fee as collect_creator_fee_cmd,
)
from pumpfun_cli.commands.trade import (
    migrate as migrate_cmd,
)
from pumpfun_cli.commands.trade import (
    sell as sell_cmd,
)

app.command("buy")(buy_cmd)
app.command("sell")(sell_cmd)
app.command("claim-cashback")(claim_cashback_cmd)
app.command("close-volume-acc")(close_volume_acc_cmd)
app.command("migrate")(migrate_cmd)
app.command("collect-creator-fee")(collect_creator_fee_cmd)

from pumpfun_cli.commands.tx_status import tx_status as tx_status_cmd

app.command("tx-status")(tx_status_cmd)
