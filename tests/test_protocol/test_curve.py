"""BondingCurve decoding at every account length."""

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import USDC_MINT, WSOL_MINT
from pumpfun_cli.protocol.curve import parse_bonding_curve
from tests.test_core.helpers import CREATOR, build_curve_data


@pytest.mark.parametrize("length", [125, 151, 256])
def test_parses_every_allocation_size(length):
    state = parse_bonding_curve(
        build_curve_data(length=length, creator_fee_bps=100, holder_reward=True, mayhem=True)
    )
    assert state["virtual_quote_reserves"] == 30_000_000_000
    assert state["creator"] == CREATOR
    assert state["is_mayhem_mode"] is True
    assert state["creator_fee_bps"] == 100
    assert state["is_holder_reward"] is True


def test_sol_paired_curve_normalizes_to_wsol():
    state = parse_bonding_curve(build_curve_data())
    assert state["quote_mint"] == WSOL_MINT
    assert state["is_sol_paired"] is True


def test_non_sol_quote_mint_is_kept():
    state = parse_bonding_curve(build_curve_data(quote_mint=USDC_MINT))
    assert state["quote_mint"] == USDC_MINT
    assert state["is_sol_paired"] is False


def test_short_curve_reports_new_fields_as_absent():
    state = parse_bonding_curve(build_curve_data(length=115))
    assert state["creator_fee_bps"] is None
    assert state["is_holder_reward"] is None


def test_curve_without_flags_is_refused():
    with pytest.raises(ValueError):
        parse_bonding_curve(build_curve_data(length=82))


def test_wrong_discriminator_is_refused():
    data = bytearray(build_curve_data())
    data[0] ^= 0xFF
    with pytest.raises(ValueError):
        parse_bonding_curve(bytes(data))


def test_holder_reward_curve_creator_is_read_as_stored():
    pda = Pubkey.new_unique()
    assert parse_bonding_curve(build_curve_data(creator=pda))["creator"] == pda
