"""Exact conversion of user-entered amounts into raw on-chain units."""

from decimal import ROUND_DOWN, Decimal


def to_raw(amount: float | str, decimals: int) -> int:
    """Whole units to raw units, exact for the decimal text the user typed.

    Goes through the decimal string rather than a float product, which can
    drop a raw unit: int(0.57 * 100) is 56.
    """
    scaled = Decimal(str(amount)) * (Decimal(10) ** decimals)
    return int(scaled.to_integral_value(ROUND_DOWN))


def amount_fields(name: str, raw: int, decimals: int) -> dict:
    """An amount for output: `name` in whole units for reading, `name_raw` exact.

    The float can lose precision on large raw counts; `name_raw` is what was
    actually used on chain.
    """
    return {name: raw / 10**decimals, f"{name}_raw": raw}
