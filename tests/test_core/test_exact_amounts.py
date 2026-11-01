"""Every reported amount carries an exact `_raw` twin, and what is sent is exact."""

from pathlib import Path
from unittest.mock import patch

from solders.pubkey import Pubkey
from solders.system_program import decode_transfer

from pumpfun_cli.core.amounts import amount_fields
from pumpfun_cli.core.pumpswap import buy_pumpswap, sell_pumpswap
from pumpfun_cli.core.trade import buy_token, collect_creator_fees, sell_token
from pumpfun_cli.core.wallet import transfer_sol
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import derive_creator_vault, find_ata
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM
from tests.test_core.helpers import (
    COIN,
    FakeClient,
    add_pool,
    build_curve_data,
    chain_with_coin,
)

MINT_STR = str(COIN)
# A count the float round trip turns into one raw unit less.
LOSSY_RAW = 65_758_096_180


def _user(tmp_keystore):
    return decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()


def test_amount_fields_keeps_the_exact_count():
    fields = amount_fields("tokens_sold", LOSSY_RAW, 6)
    assert fields["tokens_sold_raw"] == LOSSY_RAW
    assert int(fields["tokens_sold"] * 10**6) == LOSSY_RAW - 1  # why the twin exists


async def test_bonding_curve_buy_and_sell_report_raw(tmp_keystore):
    client = chain_with_coin()
    client.token_balances[find_ata(_user(tmp_keystore), COIN, TOKEN_2022_PROGRAM)] = LOSSY_RAW
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        bought = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.00013)
        sold = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
        dry = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", dry_run=True
        )
    assert bought["quote_spent_raw"] == 130_000
    assert isinstance(bought["tokens_received_raw"], int)
    assert sold["tokens_sold_raw"] == LOSSY_RAW
    assert dry["tokens_in_raw"] == LOSSY_RAW
    assert {"expected_quote_raw", "min_quote_out_raw"} <= set(dry)


async def test_pumpswap_reports_raw(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    add_pool(client)
    client.token_balances[find_ata(_user(tmp_keystore), COIN, TOKEN_2022_PROGRAM)] = LOSSY_RAW
    with patch("pumpfun_cli.core.pumpswap.RpcClient", return_value=client):
        bought = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.00013, dry_run=True
        )
        sold = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert bought["quote_in_raw"] == 130_000
    assert {"expected_tokens_raw", "min_tokens_out_raw"} <= set(bought)
    assert sold["tokens_sold_raw"] == LOSSY_RAW


async def test_collect_reports_raw(tmp_keystore):
    client = FakeClient()
    client.balances[derive_creator_vault(_user(tmp_keystore))] = 650_240 + 123_456_789
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["pump_recovered_raw"] == 123_456_789


async def test_sol_transfer_sends_the_exact_amount(tmp_keystore):
    client = FakeClient()
    recipient = Pubkey.new_unique()
    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=client):
        result = await transfer_sol(
            "http://rpc", tmp_keystore, "testpass", str(recipient), 0.00013
        )
    sent = decode_transfer(client.sent[0]["instructions"][0])
    assert int(0.00013 * 10**9) == 129_999  # what the float conversion sent
    assert sent["lamports"] == 130_000
    assert result["sol_amount_raw"] == 130_000
