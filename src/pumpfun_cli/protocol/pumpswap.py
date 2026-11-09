"""PumpSwap AMM pool discovery, parsing, and price calculation."""

import random
import struct

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import derive_amm_pool
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import (
    DEFAULT_PUBKEY,
    GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET,
    GLOBALCONFIG_COIN_CREATOR_FEE_BPS_OFFSET,
    GLOBALCONFIG_LP_FEE_BPS_OFFSET,
    GLOBALCONFIG_PROTOCOL_FEE_BPS_OFFSET,
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENTS_OFFSET,
    GLOBALCONFIG_RESERVED_FEE_RECIPIENT_OFFSET,
    POOL_CASHBACK_OFFSET,
    POOL_MAYHEM_MODE_OFFSET,
    POOL_VIRTUAL_QUOTE_RESERVES_OFFSET,
    PUMP_SWAP_GLOBAL_CONFIG,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.quote import get_mint_info


class PoolNotFoundError(RuntimeError):
    """The coin has no canonical PumpSwap pool."""


async def get_pool_by_mint(
    client: RpcClient, mint: Pubkey, quote_mint: Pubkey = WSOL_MINT
) -> tuple[Pubkey, bytes]:
    """Find the canonical PumpSwap pool a pump.fun coin graduated into.

    The address is derived from the mint and the curve's quote mint, then read
    with a single getAccountInfo.

    Raises:
        PoolNotFoundError: If the pool does not exist
        RuntimeError: If the pool cannot be read
    """
    pool_address = derive_amm_pool(mint, quote_mint)
    try:
        resp = await client.get_account_info(pool_address)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch PumpSwap pool {pool_address}: {exc}") from exc
    if not resp.value:
        raise PoolNotFoundError(f"No PumpSwap pool found for {mint}")
    return pool_address, bytes(resp.value.data)


def _flag(data: bytes, offset: int) -> bool:
    return len(data) > offset and bool(data[offset])


def parse_pool_data(data: bytes) -> dict:
    """Parse a PumpSwap Pool account.

    Layout, discriminator included: pool_bump u8 (8), index u16 (9), creator (11),
    base_mint (43), quote_mint (75), lp_mint (107), pool_base_token_account
    (139), pool_quote_token_account (171), lp_supply u64 (203), coin_creator
    (211), is_mayhem_mode (243), is_cashback_coin (244), virtual_quote_reserves
    i128 (245).

    `coin_creator` is set only on a canonical pool, one that graduated from a
    pump.fun curve; every other pool carries the default pubkey.
    """
    virtual_end = POOL_VIRTUAL_QUOTE_RESERVES_OFFSET + 16
    virtual_quote = (
        int.from_bytes(data[POOL_VIRTUAL_QUOTE_RESERVES_OFFSET:virtual_end], "little", signed=True)
        if len(data) >= virtual_end
        else 0
    )
    coin_creator = Pubkey.from_bytes(data[211:243])
    return {
        "pool_bump": data[8],
        "index": struct.unpack_from("<H", data, 9)[0],
        "creator": Pubkey.from_bytes(data[11:43]),
        "base_mint": Pubkey.from_bytes(data[43:75]),
        "quote_mint": Pubkey.from_bytes(data[75:107]),
        "lp_mint": Pubkey.from_bytes(data[107:139]),
        "pool_base_token_account": Pubkey.from_bytes(data[139:171]),
        "pool_quote_token_account": Pubkey.from_bytes(data[171:203]),
        "lp_supply": struct.unpack_from("<Q", data, 203)[0],
        "coin_creator": coin_creator,
        "is_canonical": coin_creator != DEFAULT_PUBKEY,
        "is_mayhem_mode": _flag(data, POOL_MAYHEM_MODE_OFFSET),
        "is_cashback_coin": _flag(data, POOL_CASHBACK_OFFSET),
        "virtual_quote_reserves": virtual_quote,
    }


def _pubkeys(data: bytes, offset: int, count: int) -> list[Pubkey]:
    return [Pubkey.from_bytes(data[offset + 32 * i : offset + 32 * (i + 1)]) for i in range(count)]


def parse_global_config(data: bytes) -> dict:
    """Parse the PumpSwap GlobalConfig fields a trade needs."""
    return {
        "lp_fee_bps": struct.unpack_from("<Q", data, GLOBALCONFIG_LP_FEE_BPS_OFFSET)[0],
        "protocol_fee_bps": struct.unpack_from("<Q", data, GLOBALCONFIG_PROTOCOL_FEE_BPS_OFFSET)[
            0
        ],
        "coin_creator_fee_bps": struct.unpack_from(
            "<Q", data, GLOBALCONFIG_COIN_CREATOR_FEE_BPS_OFFSET
        )[0],
        "protocol_fee_recipients": _pubkeys(data, GLOBALCONFIG_PROTOCOL_FEE_RECIPIENTS_OFFSET, 8),
        "reserved_fee_recipient": _pubkeys(data, GLOBALCONFIG_RESERVED_FEE_RECIPIENT_OFFSET, 1)[0],
        "buyback_fee_recipients": _pubkeys(data, GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET, 8),
    }


async def get_global_config(client: RpcClient) -> dict:
    """Read and parse PumpSwap's GlobalConfig.

    Raises:
        RuntimeError: If the account cannot be read
    """
    resp = await client.get_account_info(PUMP_SWAP_GLOBAL_CONFIG)
    if not resp.value:
        raise RuntimeError("PumpSwap GlobalConfig account not found")
    return parse_global_config(bytes(resp.value.data))


def pick_fee_recipients(config: dict, is_mayhem_mode: bool) -> tuple[Pubkey, Pubkey]:
    """(protocol fee recipient, buyback fee recipient) for one trade.

    A mayhem pool pays GlobalConfig's reserved recipient; any other pool pays
    one of the eight protocol recipients, picked at random to spread contention.
    """
    if is_mayhem_mode:
        fee_recipient = config["reserved_fee_recipient"]
    else:
        fee_recipient = random.choice(config["protocol_fee_recipients"])
    return fee_recipient, random.choice(config["buyback_fee_recipients"])


async def get_token_program_id(client: RpcClient, mint: Pubkey) -> Pubkey:
    """Determine the token program (Token or Token2022) for a given mint."""
    resp = await client.get_account_info(mint)
    if not resp.value:
        raise RuntimeError(f"Mint account not found: {mint}")
    owner = resp.value.owner
    if owner in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
        return owner
    raise RuntimeError(f"Unknown token program owner: {owner}")


async def resolve_pool_tokens(client: RpcClient, pool: dict) -> dict:
    """Token programs and decimals for both sides of a pool.

    Non-canonical pools routinely carry 9-decimal base tokens, so neither side
    is assumed.
    """
    base_program, base_decimals = await get_mint_info(client, pool["base_mint"])
    quote_program, quote_decimals = await get_mint_info(client, pool["quote_mint"])
    return {
        "base_token_program": base_program,
        "base_decimals": base_decimals,
        "quote_token_program": quote_program,
        "quote_decimals": quote_decimals,
    }


async def get_pool_balances(client: RpcClient, pool: dict) -> tuple[int, int]:
    """Base and effective quote reserves, raw units.

    The quote side is the vault balance plus the pool's virtual quote reserves;
    quoting off the vault alone under-prices any pool that carries some.
    """
    base_balance = await client.get_token_account_balance(pool["pool_base_token_account"])
    quote_balance = await client.get_token_account_balance(pool["pool_quote_token_account"])
    return base_balance, quote_balance + pool.get("virtual_quote_reserves", 0)


def pool_price(
    base_balance: int, quote_balance: int, base_decimals: int, quote_decimals: int
) -> float:
    """Price in whole quote units per whole base token."""
    if base_balance <= 0:
        return 0.0
    return (quote_balance / 10**quote_decimals) / (base_balance / 10**base_decimals)
