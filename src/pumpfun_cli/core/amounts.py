"""Exact conversion of user-entered amounts into raw on-chain units."""

from decimal import ROUND_DOWN, Decimal


def to_raw(amount: float | str, decimals: int) -> int:
    """Whole units to raw units, exact for the decimal text the user typed.

    Goes through the decimal string rather than a float product, which would
    turn 0.29 SOL into 289,999,999 lamports.
    """
    scaled = Decimal(str(amount)) * (Decimal(10) ** decimals)
    return int(scaled.to_integral_value(ROUND_DOWN))
