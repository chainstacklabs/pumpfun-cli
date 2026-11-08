"""CPMM buys, sells and info for graduated LaunchLab coins, on mainnet accounts."""

from unittest.mock import patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.cpmm import buy_cpmm, get_cpmm_info, sell_cpmm
from pumpfun_cli.protocol.address import find_ata
from pumpfun_cli.protocol.client import TransactionFailedError
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from pumpfun_cli.protocol.cpmm import CPMM_PROGRAM, parse_cpmm_pool, swap_amount_out
from pumpfun_cli.protocol.launchlab import withheld_fee
from tests.test_core.helpers import FakeClient, add_launchlab_fixture

SOL_FIXTURE = "cpmm_sol_pool.json"
FEE_FIXTURE = "cpmm_transfer_fee_pool.json"


def _patched(client: FakeClient):
    return (
        patch("pumpfun_cli.core.cpmm.RpcClient", return_value=client),
        patch("pumpfun_cli.core.launchlab.RpcClient", return_value=client),
    )


def _user(tmp_keystore) -> Pubkey:
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    return decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()


def _chain(fixture: str) -> tuple[FakeClient, dict, dict]:
    """The chain, each account by role, and the pool with its live reserves."""
    client = FakeClient()
    roles = add_launchlab_fixture(client, fixture)
    pool = parse_cpmm_pool(client.accounts[roles["cpmm_pool"]].data, roles["base_mint"])

    def held(vault):
        return int.from_bytes(client.accounts[vault].data[64:72], "little")

    pool["base_reserve"] = held(pool["base_vault"]) - pool["base_fees"]
    pool["quote_reserve"] = held(pool["quote_vault"]) - pool["quote_fees"]
    return client, roles, pool


async def _call(client, fn, *args, **kwargs):
    a, b = _patched(client)
    with a, b:
        return await fn(*args, **kwargs)


def _swap(client: FakeClient):
    ix = next(i for i in client.sent[0]["instructions"] if i.program_id == CPMM_PROGRAM)
    data = bytes(ix.data)
    return ix, int.from_bytes(data[8:16], "little"), int.from_bytes(data[16:24], "little")


async def test_buy_spends_exactly_the_amount(tmp_keystore):
    client, roles, pool = _chain(SOL_FIXTURE)
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.01)
    assert result["venue"] == "cpmm" and result["platform"] == "StonkFun"
    ix, amount_in, min_out = _swap(client)
    assert amount_in == 10_000_000
    expected = swap_amount_out(pool["quote_reserve"], pool["base_reserve"], amount_in, 12_500)
    assert result["tokens_received"] == expected / 10**6
    assert min_out == expected * 85 // 100
    user = _user(tmp_keystore)
    assert ix.accounts[5].pubkey == find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)


async def test_a_transfer_fee_coin_bought_with_another_quote(tmp_keystore):
    client, roles, pool = _chain(FEE_FIXTURE)
    user = _user(tmp_keystore)
    quote_ata = find_ata(user, roles["quote_mint"], TOKEN_PROGRAM)
    client.token_balances[quote_ata] = 10**8
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.5)
    ix, amount_in, min_out = _swap(client)
    assert amount_in == 5 * 10**7  # 8 decimals
    gross = swap_amount_out(pool["quote_reserve"], pool["base_reserve"], amount_in, 12_500)
    net = gross - withheld_fee(gross, ((100, 10**15),))
    assert result["tokens_received"] * 10**6 == pytest.approx(net, abs=1)
    assert min_out == net * 85 // 100
    assert ix.accounts[4].pubkey == quote_ata


async def test_buy_needs_the_quote_asset(tmp_keystore):
    client, roles, _ = _chain(FEE_FIXTURE)
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.5)
    assert result["error"] == "insufficient_balance"
    assert result["required_quote_raw"] == 5 * 10**7
    assert client.sent == []


async def test_sell_withholds_the_transfer_fee_first(tmp_keystore):
    client, roles, pool = _chain(FEE_FIXTURE)
    user = _user(tmp_keystore)
    client.token_balances[find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)] = 10**12
    mint = str(roles["base_mint"])
    result = await _call(client, sell_cpmm, "http://rpc", tmp_keystore, "testpass", mint, "all")
    ix, amount_in, min_out = _swap(client)
    assert amount_in == 10**12
    arrived = 10**12 - withheld_fee(10**12, ((100, 10**15),))
    expected = swap_amount_out(pool["base_reserve"], pool["quote_reserve"], arrived, 12_500)
    assert result["quote_received"] == expected / 10**8
    assert min_out == expected * 85 // 100
    # A sell inputs the coin: its account and vault come first.
    assert ix.accounts[4].pubkey == find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)
    assert ix.accounts[6].pubkey == pool["base_vault"]


async def test_dust_is_refused(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    user = _user(tmp_keystore)
    client.token_balances[find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)] = 1
    mint = str(roles["base_mint"])
    result = await _call(client, sell_cpmm, "http://rpc", tmp_keystore, "testpass", mint, "all")
    assert result["error"] == "dust" and client.sent == []


def _set(client: FakeClient, address: Pubkey, offset: int, value: int) -> None:
    data = bytearray(client.accounts[address].data)
    data[offset] = value
    client.accounts[address].data = bytes(data)


@pytest.mark.parametrize(
    "status,migrate_type,error",
    [(0, 1, "not_graduated"), (2, 0, "unsupported_venue")],
)
async def test_coins_without_a_cpmm_pool(tmp_keystore, status, migrate_type, error):
    client, roles, _ = _chain(SOL_FIXTURE)
    _set(client, roles["launchlab_pool"], 17, status)
    _set(client, roles["launchlab_pool"], 20, migrate_type)
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.01)
    assert result["error"] == error and client.sent == []


async def test_a_pool_not_open_yet(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    del client.accounts[roles["cpmm_pool"]]
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.01)
    assert result["error"] == "migrating"


async def test_slippage_is_reported(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    client.send_error = TransactionFailedError({"InstructionError": [3, {"Custom": 6005}]})
    mint = str(roles["base_mint"])
    result = await _call(client, buy_cpmm, "http://rpc", tmp_keystore, "testpass", mint, 0.01)
    assert result["error"] == "slippage"


async def test_info():
    client, roles, pool = _chain(SOL_FIXTURE)
    info = await _call(client, get_cpmm_info, "http://rpc", str(roles["base_mint"]))
    assert info["pool_address"] == str(roles["cpmm_pool"])
    assert info["quote_reserves"] == pool["quote_reserve"] / 10**9
    assert info["pool_fee_pct"] == 1.25
    assert info["price"] == pytest.approx(
        (pool["quote_reserve"] / 1e9) / (pool["base_reserve"] / 1e6)
    )


async def test_token_info_shows_the_cpmm_pool_of_a_graduated_coin():
    from pumpfun_cli.core.info import get_token_info

    client, roles, pool = _chain(SOL_FIXTURE)
    a, b = _patched(client)
    with a, b, patch("pumpfun_cli.core.info.RpcClient", return_value=client):
        info = await get_token_info("http://rpc", str(roles["base_mint"]))
    assert info["venue"] == "cpmm" and info["graduated"] is True
    assert info["migrate_type"] == "cpmm"
    assert info["launchlab_pool"] == str(roles["launchlab_pool"])
    assert info["pool_address"] == str(roles["cpmm_pool"])
    assert info["base_reserves"] == pool["base_reserve"] / 10**6
