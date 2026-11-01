"""BondingCurve decoding and curve math.

A curve is 125 bytes as create_v2 allocates it, 151 for older coins, and
extend_account can grow it further. Every field read here sits at a fixed
offset regardless of length, so any length is decoded the same way.
"""

import struct

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import BONDING_CURVE_DISCRIMINATOR, TOKEN_DECIMALS
from pumpfun_cli.protocol.quote import is_sol, normalize_quote_mint

# Byte offsets, discriminator included.
_RESERVES_FORMAT = (
    "<QQQQQ?"  # virtual_token, virtual_quote, real_token, real_quote, supply, complete
)
_CREATOR_OFFSET = 49
_MAYHEM_OFFSET = 81
_CASHBACK_OFFSET = 82
_QUOTE_MINT_OFFSET = 83
_CREATOR_FEE_BPS_OFFSET = 115
_IS_HOLDER_REWARD_OFFSET = 124


def parse_bonding_curve(data: bytes) -> dict:
    """Decode a BondingCurve account.

    `quote_mint` comes back normalized (wrapped SOL for a SOL-paired coin).
    `creator_fee_bps` and `is_holder_reward` are None on a curve too short to
    carry them, i.e. one created before those fields existed.

    Raises:
        ValueError: If the discriminator is wrong or the data ends before a
            field every trade needs
    """
    if data[:8] != BONDING_CURVE_DISCRIMINATOR:
        raise ValueError("Account is not a pump.fun bonding curve")
    if len(data) <= _CASHBACK_OFFSET:
        raise ValueError(f"Bonding curve data is only {len(data)} bytes")
    (
        virtual_token,
        virtual_quote,
        real_token,
        real_quote,
        supply,
        complete,
    ) = struct.unpack_from(_RESERVES_FORMAT, data, 8)

    raw_quote = (
        Pubkey.from_bytes(data[_QUOTE_MINT_OFFSET : _QUOTE_MINT_OFFSET + 32])
        if len(data) >= _QUOTE_MINT_OFFSET + 32
        else None
    )
    creator_fee_bps = (
        struct.unpack_from("<Q", data, _CREATOR_FEE_BPS_OFFSET)[0]
        if len(data) >= _CREATOR_FEE_BPS_OFFSET + 8
        else None
    )
    is_holder_reward = (
        bool(data[_IS_HOLDER_REWARD_OFFSET]) if len(data) > _IS_HOLDER_REWARD_OFFSET else None
    )
    return {
        "virtual_token_reserves": virtual_token,
        "virtual_quote_reserves": virtual_quote,
        "real_token_reserves": real_token,
        "real_quote_reserves": real_quote,
        "token_total_supply": supply,
        "complete": bool(complete),
        "creator": Pubkey.from_bytes(data[_CREATOR_OFFSET : _CREATOR_OFFSET + 32]),
        "is_mayhem_mode": bool(data[_MAYHEM_OFFSET]),
        "is_cashback_coin": bool(data[_CASHBACK_OFFSET]),
        "quote_mint": normalize_quote_mint(raw_quote),
        "is_sol_paired": is_sol(raw_quote),
        "creator_fee_bps": creator_fee_bps,
        "is_holder_reward": is_holder_reward,
    }


def calculate_buy_tokens_out(state: dict, quote_amount_raw: int) -> int:
    """Constant-product buy: raw tokens out for `quote_amount_raw`, before fees."""
    return (
        quote_amount_raw
        * state["virtual_token_reserves"]
        // (state["virtual_quote_reserves"] + quote_amount_raw)
    )


def calculate_sell_quote_out(state: dict, token_amount: int) -> int:
    """Constant-product sell: raw quote out for `token_amount` raw tokens, before fees."""
    return (
        token_amount
        * state["virtual_quote_reserves"]
        // (state["virtual_token_reserves"] + token_amount)
    )


def get_token_price(state: dict, quote_decimals: int) -> float:
    """Current price in whole quote units per whole token."""
    if state["virtual_token_reserves"] == 0:
        return 0.0
    return (state["virtual_quote_reserves"] / 10**quote_decimals) / (
        state["virtual_token_reserves"] / 10**TOKEN_DECIMALS
    )


def get_bonding_progress(state: dict, initial_real_token_reserves: int) -> float:
    """Share of the curve sold, 0.0 – 1.0, measured against Global's opening token reserves."""
    if state["complete"]:
        return 1.0
    if initial_real_token_reserves <= 0:
        return 0.0
    sold = initial_real_token_reserves - state["real_token_reserves"]
    return min(max(sold / initial_real_token_reserves, 0.0), 1.0)


def is_graduated(state: dict) -> bool:
    """Return *True* if the bonding curve is complete."""
    return bool(state["complete"])
