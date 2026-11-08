"""PumpSwap buys, sells and pool info, against an in-memory chain."""

from unittest.mock import patch

import pytest

from pumpfun_cli.core.pumpswap import buy_pumpswap, get_pumpswap_info, sell_pumpswap
from pumpfun_cli.protocol.address import (
    derive_amm_pool_v2,
    derive_amm_user_volume_accumulator,
    find_ata,
)
from pumpfun_cli.protocol.client import TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    PUMP_AMM_PROGRAM,
    PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR,
    PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR,
    PUMPSWAP_SELL_DISCRIMINATOR,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    USDC_MINT,
)
from tests.test_core.helpers import (
    BUYBACK_RECIPIENTS,
    COIN,
    PROTOCOL_RECIPIENTS,
    RESERVED_RECIPIENT,
    FakeClient,
    add_pool,
    build_curve_data,
    chain_with_coin,
)

MINT_STR = str(COIN)


def _patched(client):
    return patch("pumpfun_cli.core.pumpswap.RpcClient", return_value=client)


def _swap(sent):
    return next(
        i
        for i in sent["instructions"]
        if i.program_id == PUMP_AMM_PROGRAM
        and bytes(i.data[:8]) != PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR
    )


def _user(tmp_keystore):
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    return decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()


def _graduated_chain(**pool_kwargs):
    client = chain_with_coin(curve=build_curve_data(complete=True, virtual_quote=0))
    pool = add_pool(client, **pool_kwargs)
    return client, pool


@pytest.mark.parametrize("fn,arg", [(buy_pumpswap, 0.01), (sell_pumpswap, "all")])
async def test_invalid_mint(tmp_keystore, fn, arg):
    result = await fn("http://rpc", tmp_keystore, "testpass", "bad", arg)
    assert result["error"] == "invalid_address"


async def test_no_pool(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True))
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "pumpswap_error"
    assert result["pool_missing"] is True


async def test_no_liquidity(tmp_keystore):
    client, _ = _graduated_chain(base_reserve=0)
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "no_liquidity"


async def test_buy_sol_pool(tmp_keystore):
    client, pool = _graduated_chain()
    with _patched(client):
        result = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, slippage=10
        )
    assert result["venue"] == "pumpswap"
    assert result["quote_symbol"] == "SOL"
    sent = client.sent[0]
    swap = _swap(sent)
    assert bytes(swap.data[:8]) == PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR
    assert int.from_bytes(bytes(swap.data[8:16]), "little") == 10_000_000
    keys = [m.pubkey for m in swap.accounts]
    assert keys[0] == pool["address"]
    assert keys[9] in PROTOCOL_RECIPIENTS
    assert keys[-2] in BUYBACK_RECIPIENTS
    assert derive_amm_pool_v2(COIN) in keys
    # The accumulator is missing on this chain, so it is initialized first.
    first = sent["instructions"][0]
    assert bytes(first.data) == PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR
    # Unspent SOL comes back: the throwaway WSOL account is closed last.
    assert sent["instructions"][-1].program_id == TOKEN_PROGRAM


async def test_buy_skips_accumulator_init_when_present(tmp_keystore):
    client, _ = _graduated_chain()
    client.add(derive_amm_user_volume_accumulator(_user(tmp_keystore)), b"\x00" * 8)
    with _patched(client):
        await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    first = client.sent[0]["instructions"][0]
    assert bytes(first.data[:8]) != PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR


async def test_mayhem_pool_pays_reserved_recipient(tmp_keystore):
    client, _ = _graduated_chain(mayhem=True)
    with _patched(client):
        await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert _swap(client.sent[0]).accounts[9].pubkey == RESERVED_RECIPIENT


async def test_virtual_reserves_raise_the_quote(tmp_keystore):
    plain, _ = _graduated_chain()
    boosted, _ = _graduated_chain(virtual_quote=80_000_000_000)
    with _patched(plain):
        a = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, dry_run=True
        )
    with _patched(boosted):
        b = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, dry_run=True
        )
    assert b["spot_price"] == pytest.approx(2 * a["spot_price"])
    assert b["expected_tokens"] < a["expected_tokens"]


async def test_usdc_coin_routes_to_its_usdc_pool(tmp_keystore):
    user = _user(tmp_keystore)
    client = chain_with_coin(curve=build_curve_data(complete=True, quote_mint=USDC_MINT))
    pool = add_pool(client, quote_mint=USDC_MINT, quote_reserve=50_000_000_000)
    client.token_balances[find_ata(user, USDC_MINT, TOKEN_PROGRAM)] = 10_000_000
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 5)
    assert result["quote_symbol"] == "USDC"
    swap = _swap(client.sent[0])
    assert swap.accounts[0].pubkey == pool["address"]
    assert int.from_bytes(bytes(swap.data[8:16]), "little") == 5_000_000
    assert swap.accounts[6].pubkey == find_ata(user, USDC_MINT, TOKEN_PROGRAM)


async def test_usdc_buy_needs_usdc(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True, quote_mint=USDC_MINT))
    add_pool(client, quote_mint=USDC_MINT)
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 5)
    assert result["error"] == "insufficient_balance"


async def test_insufficient_sol(tmp_keystore):
    client, _ = _graduated_chain()
    client.default_balance = 1_000
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
        dry = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, dry_run=True
        )
    assert result["error"] == "insufficient_balance"
    assert "balance_warning" in dry
    assert client.sent == []


async def test_sell_all_non_canonical_decimals(tmp_keystore):
    """A non-canonical pool may carry a 9-decimal base token; amounts follow the mint."""
    user = _user(tmp_keystore)
    client = FakeClient()
    client.add_mint(COIN, 9, TOKEN_PROGRAM)
    add_pool(client, coin_creator=None)
    client.token_balances[find_ata(user, COIN, TOKEN_PROGRAM)] = 3_000_000_000
    with _patched(client):
        result = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["tokens_sold"] == 3.0
    swap = _swap(client.sent[0])
    assert bytes(swap.data[:8]) == PUMPSWAP_SELL_DISCRIMINATOR
    assert derive_amm_pool_v2(COIN) not in [m.pubkey for m in swap.accounts]


async def test_sell_partial_and_insufficient(tmp_keystore):
    user = _user(tmp_keystore)
    client, _ = _graduated_chain()
    client.token_balances[find_ata(user, COIN, TOKEN_2022_PROGRAM)] = 2_000_000
    with _patched(client):
        ok = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "1.5")
        too_much = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "3")
    assert int.from_bytes(bytes(_swap(client.sent[0]).data[8:16]), "little") == 1_500_000
    assert ok["tokens_sold"] == 1.5
    assert too_much["error"] == "insufficient_balance"


async def test_sell_nothing_held(tmp_keystore):
    client, _ = _graduated_chain()
    with _patched(client):
        result = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["error"] == "no_tokens"


@pytest.mark.parametrize(
    "code,error", [(6004, "slippage"), (6040, "slippage"), (6053, "tx_error")]
)
async def test_onchain_errors(tmp_keystore, code, error):
    client, _ = _graduated_chain()
    client.send_error = TransactionFailedError({"InstructionError": [4, {"Custom": code}]})
    with _patched(client):
        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == error


async def test_custom_budget_is_forwarded(tmp_keystore):
    client, _ = _graduated_chain()
    with _patched(client):
        await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            MINT_STR,
            0.01,
            priority_fee=777,
            compute_units=123_456,
        )
    assert (client.sent[0]["priority_fee"], client.sent[0]["compute_units"]) == (777, 123_456)


async def test_info():
    client, pool = _graduated_chain(base_reserve=1_000_000_000, quote_reserve=2_000_000_000)
    with _patched(client):
        info = await get_pumpswap_info("http://rpc", MINT_STR)
    assert info["pool_address"] == str(pool["address"])
    assert info["quote_symbol"] == "SOL"
    assert info["price"] == pytest.approx(2.0 / 1_000)
    assert info["base_reserves"] == 1_000.0
    assert info["quote_reserves"] == 2.0


async def test_info_without_pool():
    client = chain_with_coin()
    with _patched(client):
        info = await get_pumpswap_info("http://rpc", MINT_STR)
    assert info["error"] == "pumpswap_error"


async def test_sol_buy_wraps_ten_percent_headroom_exactly(tmp_keystore):
    client, _ = _graduated_chain()
    with _patched(client):
        await buy_pumpswap("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.29)
    from solders.system_program import ID as SYSTEM_PROGRAM_ID
    from solders.system_program import decode_create_account_with_seed

    create = next(i for i in client.sent[0]["instructions"] if i.program_id == SYSTEM_PROGRAM_ID)
    lamports = decode_create_account_with_seed(create)["lamports"]
    assert lamports - 2_039_280 == 319_000_000  # 0.29 SOL + 10%, rent on top
