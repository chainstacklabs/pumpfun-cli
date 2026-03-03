"""Additional curve tests for edge cases and missing coverage."""

from pumpfun_cli.protocol.curve import (
    get_token_price_sol,
    is_graduated,
)


def test_get_token_price_sol_zero_reserves():
    state = {"virtual_token_reserves": 0, "virtual_sol_reserves": 30_000_000_000}
    assert get_token_price_sol(state) == 0.0


def test_is_graduated_true():
    assert is_graduated({"complete": True}) is True


def test_is_graduated_false():
    assert is_graduated({"complete": False}) is False


def test_is_graduated_zero():
    assert is_graduated({"complete": 0}) is False
