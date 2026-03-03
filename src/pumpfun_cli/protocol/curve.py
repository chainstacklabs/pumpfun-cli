"""Bonding curve math — ported from pumpfun-bonkfun-bot as flat module functions."""

from pumpfun_cli.protocol.contracts import LAMPORTS_PER_SOL, TOKEN_DECIMALS

# Graduation threshold in SOL (curve completes at ~85 SOL real reserves).
_GRADUATION_SOL = 85.0


def calculate_buy_tokens_out(state: dict, sol_amount_lamports: int) -> int:
    """Constant-product AMM buy: how many tokens for *sol_amount_lamports*."""
    return (
        sol_amount_lamports
        * state["virtual_token_reserves"]
        // (state["virtual_sol_reserves"] + sol_amount_lamports)
    )


def calculate_sell_sol_out(state: dict, token_amount: int) -> int:
    """Constant-product AMM sell: how many lamports for *token_amount* tokens."""
    return (
        token_amount
        * state["virtual_sol_reserves"]
        // (state["virtual_token_reserves"] + token_amount)
    )


def get_token_price_sol(state: dict) -> float:
    """Current price in SOL per whole token (1e6 base units)."""
    if state["virtual_token_reserves"] == 0:
        return 0.0
    return (
        (state["virtual_sol_reserves"] / state["virtual_token_reserves"])
        * (10**TOKEN_DECIMALS)
        / LAMPORTS_PER_SOL
    )


def get_bonding_progress(state: dict) -> float:
    """Completion percentage as 0.0 – 1.0 (graduates at ~85 SOL)."""
    return min(
        state["real_sol_reserves"] / LAMPORTS_PER_SOL / _GRADUATION_SOL,
        1.0,
    )


def is_graduated(state: dict) -> bool:
    """Return *True* if the bonding curve is complete."""
    return bool(state["complete"])
