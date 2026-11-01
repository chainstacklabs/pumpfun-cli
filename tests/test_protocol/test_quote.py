"""Quote assets: mint resolution, the two registries, and the launch guards."""

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import (
    DEFAULT_PUBKEY,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    USDC_MINT,
    WSOL_MINT,
)
from pumpfun_cli.protocol.quote import (
    check_creator_fee,
    check_mayhem_quote,
    decode_global,
    decode_quote_control,
    get_mint_info,
    normalize_quote_mint,
    opening_quote_reserves,
    quote_symbol,
)
from tests.test_core.helpers import (
    GLOBAL_DEFAULTS,
    FakeClient,
    build_global_data,
    build_quote_control_data,
)

QC_MINT = Pubkey.new_unique()


def test_normalize_and_symbol():
    assert normalize_quote_mint(DEFAULT_PUBKEY) == WSOL_MINT
    assert normalize_quote_mint(None) == WSOL_MINT
    assert quote_symbol(DEFAULT_PUBKEY) == "SOL"
    assert quote_symbol(USDC_MINT) == "USDC"
    assert quote_symbol(QC_MINT) == str(QC_MINT)


async def test_known_quote_mints_need_no_rpc():
    client = FakeClient()
    assert await get_mint_info(client, WSOL_MINT) == (TOKEN_PROGRAM, 9)
    assert await get_mint_info(client, USDC_MINT) == (TOKEN_PROGRAM, 6)


async def test_other_mints_are_read_from_chain():
    client = FakeClient()
    client.add_mint(QC_MINT, 8, TOKEN_2022_PROGRAM)
    assert await get_mint_info(client, QC_MINT) == (TOKEN_2022_PROGRAM, 8)


async def test_mint_owned_by_something_else_is_refused():
    client = FakeClient()
    client.add(QC_MINT, bytes(82), owner=Pubkey.new_unique())
    with pytest.raises(RuntimeError):
        await get_mint_info(client, QC_MINT)


async def test_missing_mint_is_refused():
    with pytest.raises(RuntimeError):
        await get_mint_info(FakeClient(), QC_MINT)


def test_decode_global_roundtrip():
    fields = decode_global(build_global_data())
    for key in (
        "initial_virtual_token_reserves",
        "initial_real_token_reserves",
        "fee_basis_points",
        "withdraw_authority",
        "max_configurable_creator_fee_bps",
        "is_holder_reward_enabled",
    ):
        assert fields[key] == GLOBAL_DEFAULTS[key]
    assert fields["whitelisted_quote_mints"] == [USDC_MINT]


def test_decode_global_stops_at_truncation():
    fields = decode_global(build_global_data()[:200])
    assert "fee_basis_points" in fields
    assert "is_holder_reward_enabled" not in fields


def test_decode_quote_control():
    assert decode_quote_control(build_quote_control_data({QC_MINT: 42})) == {QC_MINT: 42}
    with pytest.raises(ValueError):
        decode_quote_control(bytes(50))


GLOBAL = decode_global(build_global_data())


def test_opening_reserves_come_from_the_right_registry():
    registry = {QC_MINT: 7}
    assert (
        opening_quote_reserves(registry, WSOL_MINT, GLOBAL)
        == GLOBAL["initial_virtual_sol_reserves"]
    )
    assert opening_quote_reserves(registry, QC_MINT, GLOBAL) == 7
    assert (
        opening_quote_reserves(registry, USDC_MINT, GLOBAL)
        == GLOBAL["initial_virtual_quote_reserves"]
    )
    with pytest.raises(ValueError):
        opening_quote_reserves(registry, Pubkey.new_unique(), GLOBAL)


def test_creator_fee_only_on_a_quote_control_mint():
    registry = {QC_MINT: 7}
    check_creator_fee(GLOBAL, registry, QC_MINT, 100)
    check_creator_fee(GLOBAL, registry, WSOL_MINT, None)
    check_creator_fee(GLOBAL, registry, WSOL_MINT, 0)
    for mint in (WSOL_MINT, USDC_MINT):
        with pytest.raises(ValueError, match="store 0"):
            check_creator_fee(GLOBAL, registry, mint, 100)


def test_creator_fee_bounds():
    registry = {QC_MINT: 7}
    with pytest.raises(ValueError, match="maximum"):
        check_creator_fee(GLOBAL, registry, QC_MINT, 501)
    closed = {**GLOBAL, "creator_fee_configurable": False}
    with pytest.raises(ValueError, match="not accepting"):
        check_creator_fee(closed, registry, QC_MINT, 100)


def test_mayhem_needs_sol():
    check_mayhem_quote(WSOL_MINT, True)
    check_mayhem_quote(USDC_MINT, False)
    with pytest.raises(ValueError):
        check_mayhem_quote(USDC_MINT, True)
