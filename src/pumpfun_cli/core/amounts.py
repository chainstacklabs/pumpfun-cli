"""Exact conversion of user-entered amounts into raw on-chain units."""

import asyncio
from decimal import ROUND_DOWN, Decimal

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.client import RpcClient

# A load-balanced endpoint can briefly miss a transaction another node confirmed.
_TX_READ_ATTEMPTS = 3


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


def received_fields(name: str, actual: int | None, estimate: int, decimals: int) -> dict:
    """A trade's receipt: exact, with `name_raw`, when read from the confirmed
    transaction; otherwise the pre-trade estimate alone, without `name_raw`."""
    if actual is None:
        return {name: estimate / 10**decimals}
    return amount_fields(name, actual, decimals)


def token_delta(tx: dict, owner: Pubkey, mint: Pubkey) -> int:
    """Raw change in `owner`'s balance of `mint` across a transaction."""

    def total(rows: list) -> int:
        return sum(
            int(r["uiTokenAmount"]["amount"])
            for r in rows
            if r.get("owner") == str(owner) and r.get("mint") == str(mint)
        )

    return total(tx["post_token_balances"]) - total(tx["pre_token_balances"])


async def confirmed_token_delta(
    client: RpcClient, signature: str, owner: Pubkey, mint: Pubkey
) -> int | None:
    """Raw tokens a confirmed transaction moved into `owner`'s account, or None
    when the transaction cannot be read back."""
    for attempt in range(_TX_READ_ATTEMPTS):
        try:
            tx = await client.get_transaction(signature)
        except RuntimeError:
            return None
        if tx is not None:
            return None if tx["err"] else token_delta(tx, owner, mint)
        if attempt < _TX_READ_ATTEMPTS - 1:
            await asyncio.sleep(1)
    return None
