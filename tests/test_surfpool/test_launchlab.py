"""Surfpool integration: buy and sell forked Raydium LaunchLab coins.

Set SURFPOOL_LAUNCHLAB_MINT to a SOL-priced LaunchLab coin still on its curve,
and optionally SURFPOOL_LAUNCHLAB_QUOTE_MINT to one priced in another asset;
the test wallet is given that asset with surfnet_setTokenAccount.
"""

import os

import httpx
import pytest

from pumpfun_cli.core.info import get_token_info
from pumpfun_cli.core.launchlab import buy_launchlab, sell_launchlab


def _mint(var: str) -> str:
    mint = os.environ.get(var)
    if not mint:
        pytest.skip(f"Set {var} to a LaunchLab coin on its curve")
    return mint


async def _round_trip(rpc, keystore, password, mint, amount):
    bought = await buy_launchlab(rpc, str(keystore), password, mint, amount, 25, confirm=True)
    assert "error" not in bought, bought
    assert bought["venue"] == "launchlab"
    assert bought["tokens_received_raw"] > 0
    sold = await sell_launchlab(rpc, str(keystore), password, mint, "all", 25, confirm=True)
    assert "error" not in sold, sold
    assert sold["tokens_sold_raw"] == bought["tokens_received_raw"]
    return bought, sold


@pytest.mark.asyncio
async def test_sol_coin_round_trip(surfpool_rpc, funded_keypair, test_keystore, test_password):
    mint = _mint("SURFPOOL_LAUNCHLAB_MINT")
    info = await get_token_info(surfpool_rpc, mint)
    assert info["venue"] == "launchlab" and info["quote_symbol"] == "SOL", info
    await _round_trip(surfpool_rpc, test_keystore, test_password, mint, 0.01)


@pytest.mark.asyncio
async def test_other_quote_round_trip(surfpool_rpc, funded_keypair, test_keystore, test_password):
    mint = _mint("SURFPOOL_LAUNCHLAB_QUOTE_MINT")
    info = await get_token_info(surfpool_rpc, mint)
    assert info["venue"] == "launchlab" and info["quote_symbol"] != "SOL", info
    quote = info["quote_mint"]
    async with httpx.AsyncClient() as http:
        owner = (
            await http.post(
                surfpool_rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAccountInfo",
                    "params": [quote, {"encoding": "base64"}],
                },
            )
        ).json()["result"]["value"]["owner"]
        funded = (
            await http.post(
                surfpool_rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "surfnet_setTokenAccount",
                    "params": [str(funded_keypair.pubkey()), quote, {"amount": 10**12}, owner],
                },
            )
        ).json()
    assert "error" not in funded, funded
    bought, sold = await _round_trip(surfpool_rpc, test_keystore, test_password, mint, 1)
    assert bought["quote_mint"] == quote and sold["quote_received"] > 0
