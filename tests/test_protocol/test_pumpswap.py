"""Tests for PumpSwap pool parsing and PDA derivation."""

import struct

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_amm_creator_vault,
    derive_amm_fee_config,
    derive_amm_global_volume_accumulator,
    derive_amm_user_volume_accumulator,
)
from pumpfun_cli.protocol.pumpswap import parse_pool_data

_USER = Pubkey.from_string("11111111111111111111111111111112")
_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


def _build_pool_data() -> bytes:
    """Build a synthetic pool data blob for testing parse_pool_data."""
    creator = bytes(_USER)
    base_mint = bytes(_MINT)
    quote_mint = bytes(Pubkey.from_string("So11111111111111111111111111111111111111112"))
    lp_mint = bytes(Pubkey.from_string("11111111111111111111111111111113"))
    pool_base_token = bytes(Pubkey.from_string("11111111111111111111111111111114"))
    pool_quote_token = bytes(Pubkey.from_string("11111111111111111111111111111115"))
    coin_creator = bytes(_USER)

    data = bytearray(243)
    # discriminator (8 bytes)
    data[0:8] = b"\x00" * 8
    # pool_bump (1 byte at offset 8)
    data[8] = 255
    # index (u16 at offset 9)
    struct.pack_into("<H", data, 9, 42)
    # creator (32 bytes at offset 11)
    data[11:43] = creator
    # base_mint (32 bytes at offset 43)
    data[43:75] = base_mint
    # quote_mint (32 bytes at offset 75)
    data[75:107] = quote_mint
    # lp_mint (32 bytes at offset 107)
    data[107:139] = lp_mint
    # pool_base_token_account (32 bytes at offset 139)
    data[139:171] = pool_base_token
    # pool_quote_token_account (32 bytes at offset 171)
    data[171:203] = pool_quote_token
    # lp_supply (u64 at offset 203)
    struct.pack_into("<Q", data, 203, 1_000_000)
    # coin_creator (32 bytes at offset 211)
    data[211:243] = coin_creator

    return bytes(data)


def test_parse_pool_data_fields():
    data = _build_pool_data()
    pool = parse_pool_data(data)
    assert pool["pool_bump"] == 255
    assert pool["index"] == 42
    assert pool["creator"] == _USER
    assert pool["base_mint"] == _MINT
    assert pool["lp_supply"] == 1_000_000
    assert pool["coin_creator"] == _USER


def test_parse_pool_data_token_accounts():
    data = _build_pool_data()
    pool = parse_pool_data(data)
    assert pool["pool_base_token_account"] == Pubkey.from_string(
        "11111111111111111111111111111114"
    )
    assert pool["pool_quote_token_account"] == Pubkey.from_string(
        "11111111111111111111111111111115"
    )


# --- PDA derivation tests ---


def test_amm_creator_vault_deterministic():
    a = derive_amm_creator_vault(_USER)
    b = derive_amm_creator_vault(_USER)
    assert a == b


def test_amm_creator_vault_differs_from_pump_creator_vault():
    from pumpfun_cli.protocol.address import derive_creator_vault

    amm_vault = derive_amm_creator_vault(_USER)
    pump_vault = derive_creator_vault(_USER)
    assert amm_vault != pump_vault


def test_amm_fee_config_deterministic():
    assert derive_amm_fee_config() == derive_amm_fee_config()


def test_amm_fee_config_differs_from_pump_fee_config():
    from pumpfun_cli.protocol.address import find_fee_config

    assert derive_amm_fee_config() != find_fee_config()


def test_amm_global_volume_accumulator_deterministic():
    assert derive_amm_global_volume_accumulator() == derive_amm_global_volume_accumulator()


def test_amm_user_volume_accumulator_deterministic():
    a = derive_amm_user_volume_accumulator(_USER)
    b = derive_amm_user_volume_accumulator(_USER)
    assert a == b


def test_amm_user_volume_differs_from_pump():
    from pumpfun_cli.protocol.address import find_user_volume_accumulator

    amm = derive_amm_user_volume_accumulator(_USER)
    pump = find_user_volume_accumulator(_USER)
    assert amm != pump


# --- Pool PDA derivation tests ---


def test_derive_amm_pool_deterministic():
    """derive_amm_pool returns the same address for the same mint."""
    from pumpfun_cli.protocol.address import derive_amm_pool

    a = derive_amm_pool(_MINT)
    b = derive_amm_pool(_MINT)
    assert a == b


def test_derive_amm_pool_matches_migrate_derivation():
    """derive_amm_pool produces the same PDA as build_migrate_instruction's inline derivation."""
    from pumpfun_cli.protocol.address import derive_amm_pool, derive_pool_authority
    from pumpfun_cli.protocol.contracts import PUMP_AMM_PROGRAM, WSOL_MINT

    pool_authority = derive_pool_authority(_MINT)
    expected, _ = Pubkey.find_program_address(
        [b"pool", bytes([0, 0]), bytes(pool_authority), bytes(_MINT), bytes(WSOL_MINT)],
        PUMP_AMM_PROGRAM,
    )
    assert derive_amm_pool(_MINT) == expected


def test_derive_amm_pool_differs_per_mint():
    """Different mints produce different pool addresses."""
    from pumpfun_cli.protocol.address import derive_amm_pool

    other_mint = Pubkey.from_string("So11111111111111111111111111111111111111112")
    assert derive_amm_pool(_MINT) != derive_amm_pool(other_mint)
