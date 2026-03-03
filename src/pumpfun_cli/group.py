"""Custom Click group that accepts --json at any position."""

import click
from typer.core import TyperGroup


class JsonAwareGroup(TyperGroup):
    """TyperGroup that extracts --json from args before parsing.

    This allows ``--json`` to appear after the subcommand (trailing),
    not only before it (leading). The flag is stored in ``ctx.meta``
    so the root callback can pick it up.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Remove all ``--json`` tokens and record override in ctx.meta."""
        if "--json" in args:
            args = [a for a in args if a != "--json"]
            ctx.meta["json_override"] = True
        return super().parse_args(ctx, args)
