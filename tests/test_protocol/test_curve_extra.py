"""Curve math: constant-product quotes, price and graduation progress."""

import pytest

from pumpfun_cli.protocol.curve import (
    calculate_buy_tokens_out,
    calculate_sell_quote_out,
    get_bonding_progress,
    get_token_price,
    is_graduated,
)

STATE = {
    "virtual_token_reserves": 1_000_000_000_000_000,
    "virtual_quote_reserves": 30_000_000_000,
    "real_token_reserves": 700_000_000_000_000,
    "complete": False,
}


def test_buy_and_sell_are_constant_product():
    tokens = calculate_buy_tokens_out(STATE, 1_000_000_000)
    assert tokens == 1_000_000_000 * 1_000_000_000_000_000 // 31_000_000_000
    assert calculate_sell_quote_out(STATE, tokens) < 1_000_000_000


@pytest.mark.parametrize("decimals,expected", [(9, 3e-8), (6, 3e-5)])
def test_price_scales_by_quote_decimals(decimals, expected):
    assert get_token_price(STATE, decimals) == pytest.approx(expected)


def test_price_of_empty_curve_is_zero():
    assert get_token_price({**STATE, "virtual_token_reserves": 0}, 9) == 0.0


def test_progress_against_global_opening_reserves():
    assert get_bonding_progress(STATE, 800_000_000_000_000) == pytest.approx(0.125)
    assert get_bonding_progress({**STATE, "complete": True}, 800_000_000_000_000) == 1.0
    assert get_bonding_progress(STATE, 0) == 0.0


def test_is_graduated():
    assert is_graduated({"complete": True})
    assert not is_graduated({"complete": False})
