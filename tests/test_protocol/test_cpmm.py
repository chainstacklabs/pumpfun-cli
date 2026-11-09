"""Raydium CPMM: layouts against mainnet accounts, and the swap instruction."""

import base64
import json
import struct
from pathlib import Path

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM, WSOL_MINT
from pumpfun_cli.protocol.cpmm import (
    CPMM_AUTHORITY,
    CPMM_PROGRAM,
    SWAP_BASE_INPUT_DISCRIMINATOR,
    build_cpmm_swap_instruction,
    cpmm_pool_address,
    parse_cpmm_fee_rate,
    parse_cpmm_pool,
    swap_amount_out,
)
from pumpfun_cli.protocol.launchlab import PLATFORM_CPSWAP_CONFIG_OFFSET

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _fixture(name: str) -> dict:
    """A migrated LaunchLab coin and its CPMM pool, as they were on mainnet."""
    bundle = json.loads((FIXTURES / name).read_text())
    return {key: {**acc, "bytes": base64.b64decode(acc["data"])} for key, acc in bundle.items()}


SOL = _fixture("cpmm_sol_pool.json")
FEE = _fixture("cpmm_transfer_fee_pool.json")


def _mint(bundle: dict) -> Pubkey:
    return Pubkey.from_string(bundle["base_mint"]["address"])


@pytest.mark.parametrize("bundle", [SOL, FEE], ids=["sol", "transfer_fee"])
def test_the_pool_derives_from_the_platforms_amm_config(bundle):
    config = bundle["platform_config"]["bytes"]
    amm_config = Pubkey.from_bytes(
        config[PLATFORM_CPSWAP_CONFIG_OFFSET : PLATFORM_CPSWAP_CONFIG_OFFSET + 32]
    )
    assert str(amm_config) == bundle["amm_config"]["address"]
    quote = Pubkey.from_string(bundle["quote_mint"]["address"])
    assert cpmm_pool_address(amm_config, _mint(bundle), quote) == Pubkey.from_string(
        bundle["cpmm_pool"]["address"]
    )
    # Either mint order derives the same pool.
    assert cpmm_pool_address(amm_config, quote, _mint(bundle)) == cpmm_pool_address(
        amm_config, _mint(bundle), quote
    )


@pytest.mark.parametrize("bundle", [SOL, FEE], ids=["sol", "transfer_fee"])
def test_pool_state_decodes_a_mainnet_pool(bundle):
    pool = parse_cpmm_pool(bundle["cpmm_pool"]["bytes"], _mint(bundle))
    assert str(pool["quote_mint"]) == bundle["quote_mint"]["address"]
    assert str(pool["amm_config"]) == bundle["amm_config"]["address"]
    assert pool["base_token_program"] == TOKEN_2022_PROGRAM
    assert pool["quote_token_program"] == TOKEN_PROGRAM
    assert pool["base_decimals"] == 6
    vaults = {bundle[k]["address"]: bundle[k]["bytes"] for k in ("token_0_vault", "token_1_vault")}
    base_vault, quote_vault = vaults[str(pool["base_vault"])], vaults[str(pool["quote_vault"])]
    # Each vault is a token account of its own mint, held by the CPMM authority.
    assert base_vault[:32] == bytes(_mint(bundle)) and base_vault[32:64] == bytes(CPMM_AUTHORITY)
    assert quote_vault[:32] == bytes(pool["quote_mint"])
    assert 0 <= pool["quote_fees"] < int.from_bytes(quote_vault[64:72], "little")


def test_pool_state_rejects_other_accounts_and_mints():
    with pytest.raises(ValueError):
        parse_cpmm_pool(SOL["amm_config"]["bytes"], _mint(SOL))
    with pytest.raises(ValueError):
        parse_cpmm_pool(SOL["cpmm_pool"]["bytes"], Pubkey.new_unique())


def test_fee_rate_from_a_mainnet_amm_config():
    data = SOL["amm_config"]["bytes"]
    assert parse_cpmm_fee_rate(data, creator_fee_enabled=True) == 12_500
    assert parse_cpmm_fee_rate(data, creator_fee_enabled=False) == 2_500


def test_swap_output_takes_the_fee_off_the_input():
    net = 10**9 - 12_500_000
    assert swap_amount_out(30 * 10**9, 10**15, 10**9, 12_500) == 10**15 * net // (30 * 10**9 + net)


@pytest.mark.parametrize("buy", [True, False])
def test_swap_puts_the_input_side_first(buy):
    pool = parse_cpmm_pool(SOL["cpmm_pool"]["bytes"], _mint(SOL))
    user, base_ata, quote_acc = Pubkey.new_unique(), Pubkey.new_unique(), Pubkey.new_unique()
    pool_address = Pubkey.from_string(SOL["cpmm_pool"]["address"])
    ix = build_cpmm_swap_instruction(
        buy=buy,
        pool_address=pool_address,
        pool=pool,
        user=user,
        user_base_token=base_ata,
        user_quote_token=quote_acc,
        amount_in=7,
        minimum_amount_out=3,
    )
    assert ix.program_id == CPMM_PROGRAM
    assert bytes(ix.data) == SWAP_BASE_INPUT_DISCRIMINATOR + struct.pack("<QQ", 7, 3)
    keys = [m.pubkey for m in ix.accounts]
    base = [base_ata, pool["base_vault"], TOKEN_2022_PROGRAM, _mint(SOL)]
    quote = [quote_acc, pool["quote_vault"], TOKEN_PROGRAM, WSOL_MINT]
    first, second = (quote, base) if buy else (base, quote)
    assert keys[:4] == [user, CPMM_AUTHORITY, pool["amm_config"], pool_address]
    assert keys[4:12] == [
        first[0],
        second[0],
        first[1],
        second[1],
        first[2],
        second[2],
        first[3],
        second[3],
    ]
    assert keys[12] == pool["observation"]
    writable = [m.is_writable for m in ix.accounts]
    assert writable == [
        True,
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        True,
    ]
    assert ix.accounts[0].is_signer and not any(m.is_signer for m in ix.accounts[1:])
