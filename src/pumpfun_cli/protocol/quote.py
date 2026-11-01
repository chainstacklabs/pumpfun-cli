"""Quote assets: the mint a coin is priced in, its token program and decimals.

pump.fun prices coins in SOL, USDC and a list of other mints admitted by two
on-chain registries. Amounts on the wire are in the quote mint's raw units, so
its decimals are read from chain rather than assumed: a wrong power of ten
scales the price and the slippage cap in the same direction.
"""

import struct
from typing import Any

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import find_quote_control
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import (
    DEFAULT_PUBKEY,
    KNOWN_QUOTE_MINTS,
    MINT_DECIMALS_OFFSET,
    PUMP_GLOBAL,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    USDC_MINT,
    WSOL_MINT,
)


def normalize_quote_mint(quote_mint: Pubkey | None) -> Pubkey:
    """Wrapped SOL for a SOL-paired coin's all-zero quote_mint, else the mint unchanged."""
    if quote_mint is None or quote_mint == DEFAULT_PUBKEY:
        return WSOL_MINT
    return quote_mint


def is_sol(quote_mint: Pubkey | None) -> bool:
    return normalize_quote_mint(quote_mint) == WSOL_MINT


def quote_symbol(quote_mint: Pubkey) -> str:
    """A short label for output: SOL, USDC, or the mint address for anything else."""
    if is_sol(quote_mint):
        return "SOL"
    if quote_mint == USDC_MINT:
        return "USDC"
    return str(quote_mint)


def parse_mint_account(owner: Pubkey, data: bytes) -> tuple[Pubkey, int]:
    """Token program and decimals from a raw mint account.

    Raises:
        ValueError: If the owner is not a token program or the data is too short
    """
    if owner not in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
        raise ValueError(f"Account is owned by {owner}, not by a token program")
    if len(data) <= MINT_DECIMALS_OFFSET:
        raise ValueError(f"Account data is {len(data)} bytes, too short for a mint")
    return owner, data[MINT_DECIMALS_OFFSET]


async def get_mint_info(client: RpcClient, mint: Pubkey) -> tuple[Pubkey, int]:
    """Token program and decimals for any mint, from one getAccountInfo.

    WSOL and USDC are answered without an RPC call.

    Raises:
        RuntimeError: If the mint does not exist or is not a token mint
    """
    known = KNOWN_QUOTE_MINTS.get(mint)
    if known is not None:
        return known
    resp = await client.get_account_info(mint)
    if not resp.value:
        raise RuntimeError(f"Mint account not found: {mint}")
    try:
        return parse_mint_account(resp.value.owner, bytes(resp.value.data))
    except ValueError as exc:
        raise RuntimeError(f"{mint}: {exc}") from exc


# Global's fields in declaration order, walked rather than indexed, so a field
# added at the end leaves every earlier one readable.
_GLOBAL_LAYOUT: tuple[tuple[str, str], ...] = (
    ("initialized", "bool"),
    ("authority", "pubkey"),
    ("fee_recipient", "pubkey"),
    ("initial_virtual_token_reserves", "u64"),
    ("initial_virtual_sol_reserves", "u64"),
    ("initial_real_token_reserves", "u64"),
    ("token_total_supply", "u64"),
    ("fee_basis_points", "u64"),
    ("withdraw_authority", "pubkey"),
    ("enable_migrate", "bool"),
    ("pool_migration_fee", "u64"),
    ("creator_fee_basis_points", "u64"),
    ("fee_recipients", "pubkey[7]"),
    ("set_creator_authority", "pubkey"),
    ("admin_set_creator_authority", "pubkey"),
    ("create_v2_enabled", "bool"),
    ("whitelist_pda", "pubkey"),
    ("reserved_fee_recipient", "pubkey"),
    ("mayhem_mode_enabled", "bool"),
    ("reserved_fee_recipients", "pubkey[7]"),
    ("is_cashback_enabled", "bool"),
    ("buyback_fee_recipients", "pubkey[8]"),
    ("buyback_basis_points", "u64"),
    ("initial_virtual_quote_reserves", "u64"),
    ("whitelisted_quote_mints", "pubkey[1]"),
    ("creator_fee_configurable", "bool"),
    ("max_configurable_creator_fee_bps", "u64"),
    ("holder_reward_claim_authority", "pubkey"),
    ("is_holder_reward_enabled", "bool"),
)
_GLOBAL_SIZES = {"bool": 1, "u64": 8, "pubkey": 32}


def decode_global(data: bytes) -> dict[str, Any]:
    """Decode pump.fun's Global account, stopping at the last field the data holds."""
    fields: dict[str, Any] = {}
    offset = 8
    for name, kind in _GLOBAL_LAYOUT:
        base, _, count = kind.partition("[")
        repeat = int(count.rstrip("]")) if count else 1
        width = _GLOBAL_SIZES[base] * repeat
        if offset + width > len(data):
            break
        chunk = data[offset : offset + width]
        if base == "bool":
            fields[name] = bool(chunk[0])
        elif base == "u64":
            fields[name] = struct.unpack("<Q", chunk)[0]
        elif count:
            fields[name] = [Pubkey.from_bytes(chunk[i : i + 32]) for i in range(0, width, 32)]
        else:
            fields[name] = Pubkey.from_bytes(chunk)
        offset += width
    return fields


async def fetch_global(client: RpcClient) -> dict[str, Any]:
    """Read and decode pump.fun's Global account.

    Raises:
        RuntimeError: If the account cannot be read
    """
    resp = await client.get_account_info(PUMP_GLOBAL)
    if not resp.value:
        raise RuntimeError("pump.fun Global account not found")
    return decode_global(bytes(resp.value.data))


# QuoteControl: discriminator, admin (32), 64 reserved bytes, then a vec of
# (mint, initial_virtual_quote_reserves u64).
_QUOTE_CONTROL_MINTS_OFFSET = 8 + 32 + 64
_QUOTE_CONTROL_ENTRY_SIZE = 32 + 8


def decode_quote_control(data: bytes) -> dict[Pubkey, int]:
    """Decode QuoteControl into quote mint -> opening virtual quote reserves (raw units).

    Raises:
        ValueError: If the account is too short to hold the vec length
    """
    if len(data) < _QUOTE_CONTROL_MINTS_OFFSET + 4:
        raise ValueError(f"QuoteControl account is only {len(data)} bytes")
    count = struct.unpack_from("<I", data, _QUOTE_CONTROL_MINTS_OFFSET)[0]
    start = _QUOTE_CONTROL_MINTS_OFFSET + 4
    entries: dict[Pubkey, int] = {}
    for index in range(count):
        at = start + index * _QUOTE_CONTROL_ENTRY_SIZE
        if at + _QUOTE_CONTROL_ENTRY_SIZE > len(data):
            break
        entries[Pubkey.from_bytes(data[at : at + 32])] = struct.unpack_from("<Q", data, at + 32)[0]
    return entries


async def fetch_quote_control(client: RpcClient) -> dict[Pubkey, int]:
    """Read and decode the QuoteControl registry.

    Raises:
        RuntimeError: If the account cannot be read
    """
    resp = await client.get_account_info(find_quote_control())
    if not resp.value:
        raise RuntimeError("pump.fun QuoteControl account not found")
    return decode_quote_control(bytes(resp.value.data))


def opening_quote_reserves(
    registry: dict[Pubkey, int], quote_mint: Pubkey, global_state: dict[str, Any]
) -> int:
    """Opening virtual quote reserves for a new coin priced in `quote_mint`.

    SOL uses Global's SOL figure, a QuoteControl mint carries its own, and a
    mint only Global whitelists (USDC) uses Global's quote figure. The figures
    differ by orders of magnitude, so an unlisted mint is refused, not defaulted.

    Raises:
        ValueError: If neither registry admits the mint
    """
    if is_sol(quote_mint):
        return global_state["initial_virtual_sol_reserves"]
    reserves = registry.get(quote_mint)
    if reserves is not None:
        return reserves
    if quote_mint in (global_state.get("whitelisted_quote_mints") or []):
        return global_state["initial_virtual_quote_reserves"]
    raise ValueError(f"pump.fun does not admit {quote_mint} as a quote asset.")


def check_creator_fee(
    global_state: dict[str, Any],
    registry: dict[Pubkey, int],
    quote_mint: Pubkey,
    creator_fee_bps: int | None,
) -> None:
    """Refuse a creator fee the program would reject or silently store as zero.

    The program applies a creator fee only on a coin priced in a mint that
    QuoteControl admits. On SOL, or on USDC, it accepts the argument and stores 0.

    Raises:
        ValueError: If the fee cannot take effect on this coin
    """
    if not creator_fee_bps:
        return
    if not global_state.get("creator_fee_configurable"):
        raise ValueError("pump.fun is not accepting a configurable creator fee right now.")
    ceiling = global_state.get("max_configurable_creator_fee_bps", 0)
    if creator_fee_bps > ceiling:
        raise ValueError(
            f"Creator fee {creator_fee_bps} bps is above the current maximum of {ceiling} bps."
        )
    if quote_mint not in registry:
        raise ValueError(
            f"A creator fee only applies to a coin priced in a QuoteControl mint, and "
            f"{quote_symbol(quote_mint)} is not one; pump.fun would store 0."
        )


def check_mayhem_quote(quote_mint: Pubkey, is_mayhem_mode: bool) -> None:
    """Refuse a mayhem coin priced in anything but SOL (the program rejects it with 6071).

    Raises:
        ValueError: If a mayhem coin is paired with a non-SOL quote asset
    """
    if is_mayhem_mode and not is_sol(quote_mint):
        raise ValueError("Mayhem mode can only be used with SOL as the quote asset.")
