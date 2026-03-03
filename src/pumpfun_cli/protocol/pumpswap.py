"""PumpSwap AMM pool discovery, parsing, and price calculation."""

import struct

from solana.rpc.types import MemcmpOpts
from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import (
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET,
    POOL_BASE_MINT_OFFSET,
    PUMP_AMM_PROGRAM,
    PUMP_SWAP_GLOBAL_CONFIG,
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    TOKEN_PROGRAM,
    WSOL_MINT,
)


async def get_pool_by_mint(client: RpcClient, mint: Pubkey) -> tuple[Pubkey, bytes]:
    """Find the PumpSwap pool for a given token mint.

    Returns (pool_address, pool_data) or raises RuntimeError if not found.
    """
    filters = [
        MemcmpOpts(offset=POOL_BASE_MINT_OFFSET, bytes=str(mint)),
    ]
    try:
        accounts = await client.get_program_accounts(PUMP_AMM_PROGRAM, filters)
    except Exception as exc:
        raise RuntimeError(f"Failed to query PumpSwap pools for {mint}: {exc}") from exc
    if not accounts:
        raise RuntimeError(f"No PumpSwap pool found for {mint}")
    pool_account = accounts[0]
    return pool_account.pubkey, bytes(pool_account.account.data)


def parse_pool_data(data: bytes) -> dict:
    """Parse binary pool account data into a dict.

    Layout (after 8-byte discriminator):
        u8   pool_bump        offset 8
        u16  index            offset 9
        pub  creator          offset 11
        pub  base_mint        offset 43
        pub  quote_mint       offset 75
        pub  lp_mint          offset 107
        pub  pool_base_token  offset 139
        pub  pool_quote_token offset 171
        u64  lp_supply        offset 203
        pub  coin_creator     offset 211
    """
    pool_bump = data[8]
    index = struct.unpack_from("<H", data, 9)[0]
    creator = Pubkey.from_bytes(data[11:43])
    base_mint = Pubkey.from_bytes(data[43:75])
    quote_mint = Pubkey.from_bytes(data[75:107])
    lp_mint = Pubkey.from_bytes(data[107:139])
    pool_base_token_account = Pubkey.from_bytes(data[139:171])
    pool_quote_token_account = Pubkey.from_bytes(data[171:203])
    lp_supply = struct.unpack_from("<Q", data, 203)[0]
    coin_creator = Pubkey.from_bytes(data[211:243])

    return {
        "pool_bump": pool_bump,
        "index": index,
        "creator": creator,
        "base_mint": base_mint,
        "quote_mint": quote_mint,
        "lp_mint": lp_mint,
        "pool_base_token_account": pool_base_token_account,
        "pool_quote_token_account": pool_quote_token_account,
        "lp_supply": lp_supply,
        "coin_creator": coin_creator,
    }


async def get_fee_recipients(
    client: RpcClient,
    pool_data: bytes,
) -> tuple[Pubkey, Pubkey]:
    """Determine fee recipient and its WSOL ATA.

    Always reads the protocol_fee_recipient from the GlobalConfig account.
    Falls back to the standard fee recipient if GlobalConfig is unavailable.

    Returns (fee_recipient, fee_recipient_wsol_ata).
    """
    resp = await client.get_account_info(PUMP_SWAP_GLOBAL_CONFIG)
    if resp.value:
        config_data = bytes(resp.value.data)
        off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET
        fee_recipient = Pubkey.from_bytes(config_data[off : off + 32])
    else:
        fee_recipient = STANDARD_PUMPSWAP_FEE_RECIPIENT

    fee_recipient_ata = get_associated_token_address(fee_recipient, WSOL_MINT, TOKEN_PROGRAM)
    return fee_recipient, fee_recipient_ata


async def get_token_program_id(client: RpcClient, mint: Pubkey) -> Pubkey:
    """Determine the token program (Token or Token2022) for a given mint."""
    from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM

    resp = await client.get_account_info(mint)
    if not resp.value:
        raise RuntimeError(f"Mint account not found: {mint}")
    owner = resp.value.owner
    if owner == TOKEN_PROGRAM:
        return TOKEN_PROGRAM
    if owner == TOKEN_2022_PROGRAM:
        return TOKEN_2022_PROGRAM
    raise RuntimeError(f"Unknown token program owner: {owner}")


async def get_pool_balances(client: RpcClient, pool: dict) -> tuple[int, int]:
    """Fetch base and quote token balances from pool accounts.

    Returns (base_balance, quote_balance) as raw integers.
    """
    base_balance = await client.get_token_account_balance(pool["pool_base_token_account"])
    quote_balance = await client.get_token_account_balance(pool["pool_quote_token_account"])
    return base_balance, quote_balance


async def get_pool_price(client: RpcClient, pool: dict) -> float:
    """Calculate current token price in SOL from pool reserves.

    Returns price as SOL per token (float).
    """
    base_balance, quote_balance = await get_pool_balances(client, pool)
    if base_balance == 0:
        return 0.0
    return quote_balance / base_balance
