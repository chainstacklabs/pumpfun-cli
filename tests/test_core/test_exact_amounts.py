"""Every reported amount carries an exact `_raw` twin, and what is sent is exact."""

from pathlib import Path
from unittest.mock import patch

from solders.pubkey import Pubkey
from solders.system_program import decode_transfer

from pumpfun_cli.core.amounts import amount_fields, token_delta
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
    # Unconfirmed, the receipts are pre-trade estimates and carry no `_raw`.
    assert "tokens_received" in bought and "tokens_received_raw" not in bought
    assert sold["tokens_sold_raw"] == LOSSY_RAW
    assert "quote_received" in sold and "quote_received_raw" not in sold
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
    assert result["pump_recovered"] == 0.123456789
    assert "pump_recovered_raw" not in result


def _balances(owner: Pubkey, amount: int) -> list[dict]:
    return [{"owner": str(owner), "mint": MINT_STR, "uiTokenAmount": {"amount": str(amount)}}]


async def test_confirmed_buy_reports_the_tokens_it_received(tmp_keystore):
    user = _user(tmp_keystore)
    client = chain_with_coin()
    client.transaction = {
        "err": None,
        "pre_token_balances": _balances(user, 5),
        "post_token_balances": _balances(user, 5 + LOSSY_RAW),
    }
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        bought = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.00013, confirm=True
        )
    assert bought["tokens_received_raw"] == LOSSY_RAW


async def test_confirmed_buy_falls_back_to_the_estimate_when_unreadable(tmp_keystore):
    client = chain_with_coin()
    with (
        patch("pumpfun_cli.core.trade.RpcClient", return_value=client),
        patch("pumpfun_cli.core.amounts.asyncio.sleep"),
    ):
        bought = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.00013, confirm=True
        )
    assert bought["tokens_received"] > 0 and "tokens_received_raw" not in bought


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


def test_token_delta_counts_a_newly_created_account():
    owner = Pubkey.new_unique()
    tx = {"pre_token_balances": [], "post_token_balances": _balances(owner, LOSSY_RAW)}
    assert token_delta(tx, owner, COIN) == LOSSY_RAW


def test_token_delta_refuses_to_guess():
    owner = Pubkey.new_unique()
    unrecorded = {"pre_token_balances": None, "post_token_balances": _balances(owner, 1)}
    ownerless = {
        "pre_token_balances": [],
        "post_token_balances": [{"mint": MINT_STR, "uiTokenAmount": {"amount": "7"}}],
    }
    assert token_delta(unrecorded, owner, COIN) is None
    assert token_delta(ownerless, owner, COIN) is None


# --- a confirmed sell reads what it was paid from the landed transaction ---


def _lamports(paid_out: int, fee: int, rent: int) -> dict:
    """A landed SOL sell: the payer gained the payout and any rent, less the fee."""
    return {
        "err": None,
        "fee": fee,
        "pre_balances": [1_000_000_000, 7],
        "post_balances": [1_000_000_000 + paid_out + rent - fee, 7],
        "pre_token_balances": [],
        "post_token_balances": [],
    }


async def test_a_confirmed_sell_reports_the_quote_it_was_paid(tmp_keystore):
    from tests.test_core.helpers import TOKEN_ACCOUNT_LAMPORTS, hold

    client = chain_with_coin()
    hold(client, _user(tmp_keystore), COIN, 5_000_000)  # selling all closes the account
    client.transaction = _lamports(123_456_789, fee=35_000, rent=TOKEN_ACCOUNT_LAMPORTS)
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        sold = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", confirm=True
        )
    assert sold["token_account_closed"] is True
    assert sold["quote_received_raw"] == 123_456_789
    assert sold["quote_received"] == 123_456_789 / 10**9


async def test_a_confirmed_partial_sell_has_no_rent_to_subtract(tmp_keystore):
    from tests.test_core.helpers import hold

    client = chain_with_coin()
    hold(client, _user(tmp_keystore), COIN, 5_000_000)
    client.transaction = _lamports(1_000, fee=5_000, rent=0)
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        sold = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "1", confirm=True
        )
    assert "token_account_closed" not in sold
    assert sold["quote_received_raw"] == 1_000


async def test_a_confirmed_pumpswap_sell_reports_the_quote_it_was_paid(tmp_keystore):
    from tests.test_core.helpers import TOKEN_ACCOUNT_LAMPORTS, hold

    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    add_pool(client)
    hold(client, _user(tmp_keystore), COIN, LOSSY_RAW)
    client.transaction = _lamports(987_654, fee=10_000, rent=TOKEN_ACCOUNT_LAMPORTS)
    with patch("pumpfun_cli.core.pumpswap.RpcClient", return_value=client):
        sold = await sell_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", confirm=True
        )
    assert sold["quote_received_raw"] == 987_654


async def test_a_confirmed_sell_in_another_quote_reads_its_token_balance(tmp_keystore):
    from tests.test_core.helpers import T22_QUOTE, hold

    user = _user(tmp_keystore)
    client = chain_with_coin(
        curve=build_curve_data(quote_mint=T22_QUOTE), quote_mint=T22_QUOTE, quote_decimals=6
    )
    hold(client, user, COIN, 1_000_000)

    def rows(amount: int) -> list[dict]:
        return [
            {"mint": str(T22_QUOTE), "owner": str(user), "uiTokenAmount": {"amount": str(amount)}}
        ]

    client.transaction = {
        "err": None,
        "fee": 5_000,
        "pre_balances": [1, 1],
        "post_balances": [1, 1],
        "pre_token_balances": rows(10),
        "post_token_balances": rows(10 + 4_321),
    }
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        sold = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", confirm=True
        )
    assert sold["quote_received_raw"] == 4_321
    assert sold["quote_received"] == 4_321 / 10**6


async def test_an_unreadable_sell_falls_back_to_the_estimate(tmp_keystore):
    from tests.test_core.helpers import hold

    client = chain_with_coin()
    hold(client, _user(tmp_keystore), COIN, 5_000_000)
    client.transaction = None  # not found on any read
    with (
        patch("pumpfun_cli.core.trade.RpcClient", return_value=client),
        patch("pumpfun_cli.core.amounts.asyncio.sleep"),
    ):
        sold = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", confirm=True
        )
    assert "quote_received" in sold and "quote_received_raw" not in sold
