"""Config management commands."""

import typer

from pumpfun_cli.core.config import delete_config_value, load_config, save_config_value
from pumpfun_cli.group import JsonAwareGroup
from pumpfun_cli.output import error, render

app = typer.Typer(
    help="Manage CLI configuration.", invoke_without_command=True, cls=JsonAwareGroup
)


@app.callback()
def _config_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(0)


@app.command("set")
def config_set(ctx: typer.Context, key: str, value: str):
    """Set a config value."""
    save_config_value(key, value)
    json_mode = ctx.obj.json_mode if ctx.obj else False
    if not render({"key": key, "value": value, "status": "saved"}, json_mode):
        typer.echo(f"Saved {key}.")


@app.command("get")
def config_get(ctx: typer.Context, key: str):
    """Get a config value."""
    config = load_config()
    val = config.get(key)
    if val is None:
        error(f"Key '{key}' not set.", hint="Run: pumpfun config list")
    json_mode = ctx.obj.json_mode if ctx.obj else False
    if not render({"key": key, "value": val}, json_mode):
        typer.echo(val)


@app.command("list")
def config_list(ctx: typer.Context):
    """List all config values."""
    config = load_config()
    state = ctx.obj
    json_mode = state.json_mode if state else False
    if not render(config, json_mode):
        if not config:
            typer.echo("No config values set.")
        for k, v in config.items():
            typer.echo(f"{k} = {v}")


@app.command("delete")
def config_delete(ctx: typer.Context, key: str):
    """Delete a config value."""
    try:
        delete_config_value(key)
    except KeyError:
        error(f"Key '{key}' not set.", hint="Run: pumpfun config list")
    json_mode = ctx.obj.json_mode if ctx.obj else False
    if not render({"key": key, "status": "deleted"}, json_mode):
        typer.echo(f"Deleted {key}.")
