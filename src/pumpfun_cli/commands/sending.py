"""Options and wording shared by every command that sends a transaction.

A command waits for its transaction's outcome by default and reports what
happened on chain. `--fast` sends without waiting, for when latency matters
more than knowing the result.
"""

import typer

from pumpfun_cli.output import error

FAST_HELP = "Send without waiting for the outcome: fastest, but whether it landed isn't checked"


def fast_option() -> bool:
    return typer.Option(False, "--fast", help=FAST_HELP)


def confirm_option() -> bool:
    # Waiting is the default now; the flag stays so existing scripts keep working.
    return typer.Option(False, "--confirm", hidden=True)


def wait_for_outcome(fast: bool, confirm: bool) -> bool:
    """Whether to wait for the transaction's outcome."""
    if fast and confirm:
        error("--fast and --confirm contradict each other; pass one.", exit_code=2)
    return not fast


def outcome(result: dict, summary: str) -> str:
    """`summary` once the transaction landed; otherwise, that it was only sent."""
    if result.get("confirmed"):
        return summary
    return f"Sent, not confirmed (--fast). Expected: {summary}"
