from pumpfun_cli.protocol.curve import (
    calculate_buy_tokens_out,
    calculate_sell_sol_out,
    get_bonding_progress,
    get_token_price_sol,
)


def _mock_state():
    return {
        "virtual_token_reserves": 1_073_000_000_000_000,
        "virtual_sol_reserves": 30_000_000_000,
        "real_sol_reserves": 0,
        "real_token_reserves": 793_100_000_000_000,
        "token_total_supply": 1_000_000_000_000_000,
        "complete": False,
    }


def test_buy_returns_positive_tokens():
    assert calculate_buy_tokens_out(_mock_state(), 100_000_000) > 0


def test_sell_returns_positive_sol():
    assert calculate_sell_sol_out(_mock_state(), 1_000_000_000) > 0


def test_buy_sell_roundtrip_loses_value():
    state = _mock_state()
    tokens = calculate_buy_tokens_out(state, 100_000_000)
    state["virtual_sol_reserves"] += 100_000_000
    state["virtual_token_reserves"] -= tokens
    sol_back = calculate_sell_sol_out(state, tokens)
    assert sol_back < 100_000_000


def test_price_is_positive():
    assert get_token_price_sol(_mock_state()) > 0


def test_bonding_progress_zero_at_start():
    state = _mock_state()
    state["real_sol_reserves"] = 0
    assert get_bonding_progress(state) == 0.0


def test_bonding_progress_capped_at_one():
    state = _mock_state()
    state["real_sol_reserves"] = 100 * 1_000_000_000
    assert get_bonding_progress(state) == 1.0
