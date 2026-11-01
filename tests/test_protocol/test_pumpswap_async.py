"""Async PumpSwap lookups against an in-memory chain."""

import pytest

from pumpfun_cli.protocol.address import derive_amm_pool
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM, USDC_MINT
from pumpfun_cli.protocol.pumpswap import (
    get_global_config,
    get_pool_balances,
    get_pool_by_mint,
    parse_pool_data,
    resolve_pool_tokens,
)
from tests.test_core.helpers import COIN, FakeClient, add_pool


async def test_pool_is_derived_from_mint_and_quote():
    client = FakeClient()
    pool = add_pool(client, quote_mint=USDC_MINT)
    address, data = await get_pool_by_mint(client, COIN, USDC_MINT)
    assert address == pool["address"] == derive_amm_pool(COIN, USDC_MINT)
    with pytest.raises(RuntimeError):
        await get_pool_by_mint(client, COIN)


async def test_effective_quote_reserves_include_virtual():
    client = FakeClient()
    add_pool(client, base_reserve=1_000, quote_reserve=2_000, virtual_quote=500)
    _, data = await get_pool_by_mint(client, COIN)
    assert await get_pool_balances(client, parse_pool_data(data)) == (1_000, 2_500)


async def test_resolve_pool_tokens_reads_both_mints():
    client = FakeClient()
    client.add_mint(COIN, 9, TOKEN_2022_PROGRAM)
    add_pool(client, quote_mint=USDC_MINT)
    _, data = await get_pool_by_mint(client, COIN, USDC_MINT)
    tokens = await resolve_pool_tokens(client, parse_pool_data(data))
    assert tokens == {
        "base_token_program": TOKEN_2022_PROGRAM,
        "base_decimals": 9,
        "quote_token_program": TOKEN_PROGRAM,
        "quote_decimals": 6,
    }


async def test_missing_global_config_raises():
    with pytest.raises(RuntimeError):
        await get_global_config(FakeClient())
