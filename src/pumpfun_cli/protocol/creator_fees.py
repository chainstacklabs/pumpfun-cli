"""Find creator fees waiting on a creator's curves and pools for a sweep.

pump.fun's newer trade instructions (bonding curve v3, PumpSwap v2) keep the
creator fee on the curve or in the pool instead of paying the creator vault. It
reaches the vault only through `sweep_creator_fee`, so a collect that skips the
sweep misses it.
"""

from dataclasses import dataclass

import base58
from solana.rpc.models import MemcmpOpts
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import (
    BONDING_CURVE_CREATOR_OFFSET,
    BONDING_CURVE_DISCRIMINATOR,
    POOL_COIN_CREATOR_OFFSET,
    POOL_DISCRIMINATOR,
    POOL_QUOTE_MINT_OFFSET,
    PUMP_AMM_PROGRAM,
    PUMP_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from pumpfun_cli.protocol.curve import parse_bonding_curve
from pumpfun_cli.protocol.pumpswap import parse_pool_data


@dataclass(frozen=True)
class WaitingCurve:
    mint: Pubkey
    amount: int


@dataclass(frozen=True)
class WaitingPool:
    address: Pubkey
    pool: dict
    amount: int


def _filters(discriminator: bytes, offset: int, key: Pubkey) -> list[MemcmpOpts]:
    return [
        MemcmpOpts(offset=0, bytes=base58.b58encode(discriminator).decode()),
        MemcmpOpts(offset=offset, bytes=str(key)),
    ]


async def _curve_mint(client: RpcClient, curve: Pubkey, quote_mint: Pubkey) -> Pubkey | None:
    """A curve does not store its mint; its own base-token account names it."""
    for program in (TOKEN_2022_PROGRAM, TOKEN_PROGRAM):
        for account in await client.get_token_accounts_by_owner(curve, program):
            mint = Pubkey.from_string(account["mint"])
            if mint != quote_mint:
                return mint
    return None


async def find_waiting_creator_fees(
    client: RpcClient, creator: Pubkey, quote_mint: Pubkey
) -> tuple[list[WaitingCurve], list[WaitingPool]]:
    """Curves and pools of `creator` priced in `quote_mint` that hold a creator fee.

    Each list is sorted largest fee first. Needs an RPC that serves
    getProgramAccounts.
    """
    curves = []
    found = await client.get_program_accounts(
        PUMP_PROGRAM, _filters(BONDING_CURVE_DISCRIMINATOR, BONDING_CURVE_CREATOR_OFFSET, creator)
    )
    for item in found:
        state = parse_bonding_curve(bytes(item.account.data))
        if state["creator_fee"] <= 0 or state["quote_mint"] != quote_mint:
            continue
        mint = await _curve_mint(client, item.pubkey, quote_mint)
        if mint is not None:
            curves.append(WaitingCurve(mint, state["creator_fee"]))

    pools = []
    found = await client.get_program_accounts(
        PUMP_AMM_PROGRAM,
        [
            *_filters(POOL_DISCRIMINATOR, POOL_COIN_CREATOR_OFFSET, creator),
            MemcmpOpts(offset=POOL_QUOTE_MINT_OFFSET, bytes=str(quote_mint)),
        ],
    )
    for item in found:
        pool = parse_pool_data(bytes(item.account.data))
        if pool["creator_fees"] > 0:
            pools.append(WaitingPool(item.pubkey, pool, pool["creator_fees"]))

    curves.sort(key=lambda c: c.amount, reverse=True)
    pools.sort(key=lambda p: p.amount, reverse=True)
    return curves, pools
