"""The pieces auto-routing is built from: a graduated curve hands off to its pool.

`commands/trade.py` retries on PumpSwap when the curve reports `graduated`;
these check that each side of that hand-off behaves.
"""

from unittest.mock import patch

from pumpfun_cli.core.pumpswap import buy_pumpswap, sell_pumpswap
from pumpfun_cli.core.trade import buy_token, sell_token
from pumpfun_cli.protocol.address import derive_bonding_curve, find_ata
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM
from tests.test_core.helpers import COIN, add_pool, build_curve_data, chain_with_coin

MINT_STR = str(COIN)


def _both(client):
    return (
        patch("pumpfun_cli.core.trade.RpcClient", return_value=client),
        patch("pumpfun_cli.core.pumpswap.RpcClient", return_value=client),
    )


async def test_graduated_buy_hands_off(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    add_pool(client)
    a, b = _both(client)
    with a, b:
        curve = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
        amm = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert curve["error"] == "graduated"
    assert amm["venue"] == "pumpswap" and amm["signature"] == "fakesig"


async def test_graduated_sell_hands_off(tmp_keystore):
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    user = decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()
    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    add_pool(client)
    client.token_balances[find_ata(user, COIN, TOKEN_2022_PROGRAM)] = 1_000_000
    a, b = _both(client)
    with a, b:
        curve = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
        amm = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert curve["error"] == "graduated"
    assert amm["venue"] == "pumpswap" and amm["tokens_sold"] == 1.0


async def test_missing_curve_is_not_graduated(tmp_keystore):
    client = chain_with_coin()
    del client.accounts[derive_bonding_curve(COIN)]
    a, b = _both(client)
    with a, b:
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "not_found"
