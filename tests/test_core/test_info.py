"""Token info from the curve, and from the pool once it has graduated."""

from unittest.mock import patch

import pytest

from pumpfun_cli.core.info import get_token_info
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM
from tests.test_core.helpers import (
    COIN,
    CREATOR,
    T22_QUOTE,
    add_pool,
    build_curve_data,
    chain_with_coin,
)

MINT_STR = str(COIN)


def _patched(client):
    return (
        patch("pumpfun_cli.core.info.RpcClient", return_value=client),
        patch("pumpfun_cli.core.pumpswap.RpcClient", return_value=client),
    )


async def _info(client, mint=MINT_STR):
    a, b = _patched(client)
    with a, b:
        return await get_token_info("http://rpc", mint)


async def test_invalid_and_missing():
    assert (await get_token_info("http://rpc", "bad"))["error"] == "invalid_address"
    client = chain_with_coin()
    client.accounts.clear()
    assert (await _info(client))["error"] == "not_found"


async def test_active_sol_curve():
    client = chain_with_coin(
        curve=build_curve_data(real_token=693_100_000_000_000, real_quote=4_000_000_000)
    )
    info = await _info(client)
    assert info["quote_symbol"] == "SOL"
    assert info["price"] == pytest.approx(3e-8)
    assert info["bonding_progress"] == pytest.approx(12.6, abs=0.1)
    assert info["real_quote_reserves"] == 4.0
    assert info["creator"] == str(CREATOR)
    assert info["graduated"] is False


async def test_custom_quote_curve_reports_its_asset_and_fee():
    client = chain_with_coin(
        curve=build_curve_data(
            quote_mint=T22_QUOTE, virtual_quote=5_000_000, creator_fee_bps=300, holder_reward=True
        ),
        quote_mint=T22_QUOTE,
        quote_decimals=6,
        quote_program=TOKEN_2022_PROGRAM,
    )
    info = await _info(client)
    assert info["quote_mint"] == str(T22_QUOTE)
    assert info["price"] == pytest.approx(5.0 / 1e9)
    assert info["creator_fee_bps"] == 300
    assert info["is_holder_reward"] is True


async def test_graduated_reads_the_pool():
    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    pool = add_pool(client, base_reserve=1_000_000_000, quote_reserve=3_000_000_000)
    info = await _info(client)
    assert info["graduated"] is True
    assert info["bonding_progress"] == 100.0
    assert info["pool_address"] == str(pool["address"])
    assert info["price"] == pytest.approx(3.0 / 1_000)


async def test_graduated_without_pool_warns():
    client = chain_with_coin(curve=build_curve_data(complete=True))
    info = await _info(client)
    assert info["pumpswap_error"] == "pumpswap_error"
    assert "PumpSwap" in info["pumpswap_warning"]


async def test_timeout_is_forwarded():
    client = chain_with_coin()
    with patch("pumpfun_cli.core.info.RpcClient", return_value=client) as cls:
        await get_token_info("http://rpc", MINT_STR, rpc_timeout=12.5)
    cls.assert_called_once_with("http://rpc", timeout=12.5)
