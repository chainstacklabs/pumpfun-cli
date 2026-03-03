"""TTY-aware output formatting — JSON for agents, Rich tables for humans."""

import json
import sys
from typing import NoReturn

from rich.console import Console
from rich.table import Table

_console = Console(stderr=True)

_json_mode: bool = False


def set_json_mode(value: bool) -> None:
    """Set module-level JSON mode for error output."""
    global _json_mode
    _json_mode = value


def is_tty() -> bool:
    return sys.stdout.isatty()


def render_json(data):
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def render_table(rows: list[dict], columns: list[tuple[str, str]]):
    """Render a Rich table to stderr.

    columns: list of (key, header_label) tuples.
    """
    table = Table(show_header=True, header_style="bold")
    for _, header in columns:
        table.add_column(header)
    for row in rows:
        table.add_row(*[str(row.get(k, "")) for k, _ in columns])
    _console.print(table)


def render(data, json_mode: bool):
    """Route to JSON or let caller handle human output."""
    if json_mode or not is_tty():
        render_json(data)
        return True
    return False


def error(message: str, hint: str | None = None, exit_code: int = 1) -> NoReturn:
    """Print error to stderr and exit. In JSON mode, also emit to stdout."""
    if _json_mode:
        print(json.dumps({"error": message, "hint": hint, "exit_code": exit_code}))
    _console.print(f"[red]Error:[/red] {message}")
    if hint:
        _console.print(f"  {hint}")
    raise SystemExit(exit_code)
