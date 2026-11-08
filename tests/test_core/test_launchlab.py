"""LaunchLab buys, sells and info, against mainnet pool accounts held in memory."""

from unittest.mock import patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.info import get_token_info
from pumpfun_cli.core.launchlab import buy_launchlab, get_launchlab_info, sell_launchlab
from pumpfun_cli.protocol.address import find_ata
from pumpfun_cli.protocol.client import TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from pumpfun_cli.protocol.launchlab import (
    BUY_EXACT_IN_DISCRIMINATOR,
    LAUNCHLAB_PROGRAM,
    SELL_EXACT_IN_DISCRIMINATOR,
    buy_amount_out,
    parse_pool_state,
    sell_amount_out,
)
from tests.test_core.helpers import FakeClient, add_launchlab_fixture

SOL_FIXTURE = "launchlab_sol_pool.json"
T22_FIXTURE = "launchlab_token2022_quote_pool.json"


def _patched(client: FakeClient):
    return patch("pumpfun_cli.core.launchlab.RpcClient", return_value=client)


def _user(tmp_keystore) -> Pubkey:
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    return decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()


def _chain(fixture: str) -> tuple[FakeClient, dict, dict]:
    client = FakeClient()
    roles = add_launchlab_fixture(client, fixture)
    pool = parse_pool_state(client.accounts[roles["pool"]].data)
    return client, roles, pool


def _swap(sent: dict):
    return next(i for i in sent["instructions"] if i.program_id == LAUNCHLAB_PROGRAM)


def _u64s(ix) -> tuple[int, int]:
    data = bytes(ix.data)
    return int.from_bytes(data[8:16], "little"), int.from_bytes(data[16:24], "little")


async def test_buy_on_a_sol_pool_spends_exactly_the_amount(tmp_keystore):
    client, roles, pool = _chain(SOL_FIXTURE)
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 0.01, slippage=10
        )
    assert result["venue"] == "launchlab"
    assert result["platform"] == "Spots.fun"
    assert result["quote_symbol"] == "SOL"
    swap = _swap(client.sent[0])
    assert bytes(swap.data[:8]) == BUY_EXACT_IN_DISCRIMINATOR
    amount_in, min_out = _u64s(swap)
    assert amount_in == 10_000_000
    expected = buy_amount_out(pool, amount_in, 17_500)
    assert result["tokens_received"] == expected / 10**6
    assert min_out == expected * 90 // 100
    # Coin account, then the throwaway WSOL account opened and closed around the swap.
    ixs = client.sent[0]["instructions"]
    assert ixs[0].program_id == ASSOCIATED_TOKEN_PROGRAM
    assert ixs[-1].program_id == TOKEN_PROGRAM
    user = _user(tmp_keystore)
    assert swap.accounts[5].pubkey == find_ata(user, roles["base_mint"], TOKEN_PROGRAM)
    assert swap.accounts[6].pubkey != find_ata(user, roles["quote_mint"], TOKEN_PROGRAM)


async def test_a_coin_priced_in_another_asset_is_found_by_searching(tmp_keystore):
    client, roles, pool = _chain(T22_FIXTURE)
    user = _user(tmp_keystore)
    quote_ata = find_ata(user, roles["quote_mint"], TOKEN_2022_PROGRAM)
    client.token_balances[quote_ata] = 5 * 10**8
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 1
        )
    assert result["platform"] == "StonkFun"
    assert result["quote_mint"] == str(roles["quote_mint"])
    swap = _swap(client.sent[0])
    amount_in, min_out = _u64s(swap)
    assert amount_in == 10**8  # the quote has 8 decimals
    # The coin's 1% transfer fee comes off what arrives.
    assert result["tokens_received"] * 10**6 == buy_amount_out(
        pool, amount_in, 12_500, ((100, 10**15),)
    )
    assert min_out == buy_amount_out(pool, amount_in, 12_500, ((100, 10**15),)) * 85 // 100
    assert swap.accounts[6].pubkey == quote_ata
    assert swap.accounts[5].pubkey == find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)
    assert swap.accounts[12].pubkey == TOKEN_2022_PROGRAM
    # No WSOL wrapping: create the coin and quote accounts, then swap.
    assert [i.program_id for i in client.sent[0]["instructions"]] == [
        ASSOCIATED_TOKEN_PROGRAM,
        ASSOCIATED_TOKEN_PROGRAM,
        LAUNCHLAB_PROGRAM,
    ]


async def test_buy_needs_the_quote_asset(tmp_keystore):
    client, roles, _ = _chain(T22_FIXTURE)
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 1
        )
    assert result["error"] == "insufficient_balance"
    assert result["available_quote_raw"] == 0 and result["required_quote_raw"] == 10**8
    assert "available_sol" not in result
    assert client.sent == []


async def test_a_curve_type_it_cannot_price_is_refused(tmp_keystore):
    client, roles, pool = _chain(SOL_FIXTURE)
    config = bytearray(client.accounts[pool["global_config"]].data)
    config[16] = 2  # linear
    client.accounts[pool["global_config"]].data = bytes(config)
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 0.01
        )
    assert result["error"] == "launchlab_error"
    assert client.sent == []


async def test_buy_dry_run_sends_nothing(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 0.01, dry_run=True
        )
    assert result["dry_run"] is True and result["venue"] == "launchlab"
    assert result["expected_tokens_raw"] > result["min_tokens_out_raw"] > 0
    assert client.sent == []


async def test_sell_all_of_a_transfer_fee_coin(tmp_keystore):
    client, roles, pool = _chain(T22_FIXTURE)
    user = _user(tmp_keystore)
    client.token_balances[find_ata(user, roles["base_mint"], TOKEN_2022_PROGRAM)] = 10**10
    with _patched(client):
        result = await sell_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), "all"
        )
    swap = _swap(client.sent[0])
    assert bytes(swap.data[:8]) == SELL_EXACT_IN_DISCRIMINATOR
    amount_in, min_out = _u64s(swap)
    assert amount_in == 10**10
    expected = sell_amount_out(pool, 10**10, 12_500, ((100, 10**15),))
    assert result["quote_received"] == expected / 10**8
    assert min_out == expected * 85 // 100


async def test_sell_more_than_held(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    with _patched(client):
        result = await sell_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), "5"
        )
    assert result["error"] == "insufficient_balance"


def _set_status(client: FakeClient, pool: Pubkey, status: int) -> None:
    data = bytearray(client.accounts[pool].data)
    data[17] = status
    client.accounts[pool].data = bytes(data)


@pytest.mark.parametrize("fn,arg", [(buy_launchlab, 0.01), (sell_launchlab, "all")])
async def test_a_graduated_curve_defers_to_its_pool(tmp_keystore, fn, arg):
    client, roles, _ = _chain(SOL_FIXTURE)
    _set_status(client, roles["pool"], 2)
    with _patched(client):
        result = await fn("http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), arg)
    assert result["error"] == "graduated"
    assert result["migrate_type"] == "cpmm"


async def test_no_pool(tmp_keystore):
    client = FakeClient()
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(Pubkey.new_unique()), 0.01
        )
    assert result["error"] == "not_found"


async def test_slippage_is_reported(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    client.send_error = TransactionFailedError({"InstructionError": [3, {"Custom": 6004}]})
    with _patched(client):
        result = await buy_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), 0.01
        )
    assert result["error"] == "slippage"


async def test_info():
    client, roles, pool = _chain(T22_FIXTURE)
    with _patched(client):
        info = await get_launchlab_info("http://rpc", str(roles["base_mint"]))
    assert info["venue"] == "launchlab"
    assert info["platform"] == "StonkFun"
    assert info["launchlab_pool"] == str(roles["pool"])
    assert info["graduated"] is False
    assert info["curve_fee_pct"] == 1.25
    assert info["transfer_fee_bps"] == 100
    assert info["bonding_progress"] == round(pool["real_base"] / pool["total_base_sell"] * 100, 1)


async def test_token_info_falls_back_to_launchlab():
    client, roles, _ = _chain(SOL_FIXTURE)
    with (
        patch("pumpfun_cli.core.info.RpcClient", return_value=client),
        _patched(client),
    ):
        info = await get_token_info("http://rpc", str(roles["base_mint"]))
    assert info["venue"] == "launchlab"
    assert info["platform"] == "Spots.fun"


async def test_a_sell_the_curve_would_pay_nothing_for_is_refused(tmp_keystore):
    client, roles, _ = _chain(SOL_FIXTURE)
    user = _user(tmp_keystore)
    client.token_balances[find_ata(user, roles["base_mint"], TOKEN_PROGRAM)] = 1
    with _patched(client):
        result = await sell_launchlab(
            "http://rpc", tmp_keystore, "testpass", str(roles["base_mint"]), "all"
        )
    assert result["error"] == "dust"
    assert client.sent == []
