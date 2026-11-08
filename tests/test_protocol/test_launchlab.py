"""Raydium LaunchLab: instructions against the IDL, layouts against mainnet accounts."""

import base64
import json
import struct
from pathlib import Path

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import SYSTEM_PROGRAM, TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from pumpfun_cli.protocol.launchlab import (
    LAUNCHLAB_PROGRAM,
    POOL_STATE_DISCRIMINATOR,
    build_launchlab_swap_instruction,
    buy_amount_out,
    curve_type,
    derive_creator_fee_vault,
    derive_launchlab_pool,
    derive_platform_fee_vault,
    mint_transfer_fee,
    parse_fee_rate,
    parse_pool_state,
    platform_name,
    sell_amount_out,
    withheld_fee,
)
from tests.test_protocol.test_instructions import assert_matches_idl

ROOT = Path(__file__).parents[2]
IDL = json.loads((ROOT / "idl" / "raydium_launchlab_idl.json").read_text())


def _fixture(name: str) -> dict:
    """A pool and its configs and mints as they were on mainnet."""
    bundle = json.loads((ROOT / "tests" / "fixtures" / name).read_text())
    return {key: {**acc, "bytes": base64.b64decode(acc["data"])} for key, acc in bundle.items()}


SOL_POOL = _fixture("launchlab_sol_pool.json")
T22_POOL = _fixture("launchlab_token2022_quote_pool.json")


def _swap(buy: bool, pool: dict, **overrides):
    args = {
        "buy": buy,
        "pool_address": Pubkey.new_unique(),
        "pool": pool,
        "user": Pubkey.new_unique(),
        "user_base_token": Pubkey.new_unique(),
        "user_quote_token": Pubkey.new_unique(),
        "base_token_program": TOKEN_PROGRAM,
        "quote_token_program": TOKEN_PROGRAM,
        "amount_in": 123,
        "minimum_amount_out": 45,
    }
    return build_launchlab_swap_instruction(**{**args, **overrides})


@pytest.mark.parametrize("buy,name", [(True, "buy_exact_in"), (False, "sell_exact_in")])
def test_swap_matches_idl(buy, name):
    pool = parse_pool_state(SOL_POOL["pool"]["bytes"])
    built = _swap(buy, pool)
    assert_matches_idl(IDL, name, built)
    assert bytes(built.data[8:]) == struct.pack("<QQQ", 123, 45, 0)
    assert built.program_id == LAUNCHLAB_PROGRAM


def test_swap_appends_system_program_and_fee_vaults():
    pool = parse_pool_state(T22_POOL["pool"]["bytes"])
    metas = _swap(True, pool).accounts
    assert len(metas) == 18
    assert metas[15].pubkey == SYSTEM_PROGRAM and not metas[15].is_writable
    assert metas[16].pubkey == derive_platform_fee_vault(
        pool["platform_config"], pool["quote_mint"]
    )
    assert metas[17].pubkey == derive_creator_fee_vault(pool["creator"], pool["quote_mint"])
    assert metas[16].is_writable and metas[17].is_writable


@pytest.mark.parametrize("bundle", [SOL_POOL, T22_POOL], ids=["sol", "token2022_quote"])
def test_pool_state_decodes_a_mainnet_pool(bundle):
    data = bundle["pool"]["bytes"]
    assert data[:8] == POOL_STATE_DISCRIMINATOR
    assert bytes(
        next(a for a in IDL["accounts"] if a["name"] == "PoolState")["discriminator"]
    ) == (POOL_STATE_DISCRIMINATOR)
    pool = parse_pool_state(data)
    assert str(pool["base_mint"]) == bundle["base_mint"]["address"]
    assert str(pool["quote_mint"]) == bundle["quote_mint"]["address"]
    assert str(pool["global_config"]) == bundle["global_config"]["address"]
    assert str(pool["platform_config"]) == bundle["platform_config"]["address"]
    assert derive_launchlab_pool(pool["base_mint"], pool["quote_mint"]) == Pubkey.from_string(
        bundle["pool"]["address"]
    )
    assert pool["status"] == 0 and pool["base_decimals"] == 6
    assert 0 <= pool["real_base"] <= pool["total_base_sell"] < pool["virtual_base"]


def test_pool_state_rejects_other_accounts():
    with pytest.raises(ValueError):
        parse_pool_state(SOL_POOL["global_config"]["bytes"])


def test_fees_and_names_from_mainnet_configs():
    sol, t22 = SOL_POOL, T22_POOL
    assert parse_fee_rate(sol["global_config"]["bytes"], sol["platform_config"]["bytes"]) == 17_500
    assert parse_fee_rate(t22["global_config"]["bytes"], t22["platform_config"]["bytes"]) == 12_500
    assert platform_name(sol["platform_config"]["bytes"]) == "Spots.fun"
    assert platform_name(t22["platform_config"]["bytes"]) == "StonkFun"


def test_transfer_fee_from_mainnet_mints():
    assert SOL_POOL["base_mint"]["owner"] == str(TOKEN_PROGRAM)
    assert mint_transfer_fee(SOL_POOL["base_mint"]["bytes"]) == ()
    assert T22_POOL["base_mint"]["owner"] == str(TOKEN_2022_PROGRAM)
    assert mint_transfer_fee(T22_POOL["base_mint"]["bytes"]) == ((100, 1_000_000_000_000_000),)


def test_withheld_fee_rounds_up_and_caps():
    assert withheld_fee(10_001, ((100, 10**9),)) == 101
    assert withheld_fee(10**12, ((100, 5),)) == 5
    assert withheld_fee(10**12, ()) == 0


def test_withheld_fee_charges_the_larger_scheduled_fee():
    # A low rate with a high cap withholds more than a high rate with a low cap.
    assert withheld_fee(10**9, ((100, 1_000), (50, 10**15))) == 5_000_000


def test_curve_type_is_read_from_mainnet_global_configs():
    assert curve_type(SOL_POOL["global_config"]["bytes"]) == 0
    assert curve_type(T22_POOL["global_config"]["bytes"]) == 0


_POOL = {
    "virtual_base": 1_073_025_605_596_382,
    "virtual_quote": 30_000_852_951,
    "real_base": 0,
    "real_quote": 0,
}


def test_buy_takes_the_fee_off_the_input_then_the_transfer_fee_off_the_output():
    amount_in, fee_rate = 1_000_000_000, 12_500
    net = amount_in - 12_500_000
    out = 1_073_025_605_596_382 * net // (30_000_852_951 + net)
    assert buy_amount_out(_POOL, amount_in, fee_rate) == out
    assert buy_amount_out(_POOL, amount_in, fee_rate, ((100, 10**15),)) == out - -(-out // 100)


def test_sell_withholds_the_transfer_fee_before_the_curve():
    amount_in, fee_rate = 10_000_000_000, 12_500
    arrived = amount_in - 100_000_000
    gross = 30_000_852_951 * arrived // (1_073_025_605_596_382 + arrived)
    expected = gross - -(-gross * fee_rate // 1_000_000)
    assert sell_amount_out(_POOL, amount_in, fee_rate, ((100, 10**15),)) == expected


def test_reserves_move_with_the_real_side():
    moved = {**_POOL, "real_base": 10**14, "real_quote": 3 * 10**9}
    assert buy_amount_out(moved, 10**9, 0) < buy_amount_out(_POOL, 10**9, 0)
