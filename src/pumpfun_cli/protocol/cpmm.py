"""Raydium CPMM, where a LaunchLab coin trades once its curve graduates.

The pool is derived, not searched for: CPMM keys it by an AMM config and the
two mints, and a LaunchLab platform names its AMM config in `cpswap_config`.
Both trade directions are `swap_base_input`, so a buy spends exactly its input.
"""

import hashlib
import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

CPMM_PROGRAM = Pubkey.from_string("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")
CPMM_AUTHORITY = Pubkey.find_program_address([b"vault_and_lp_mint_auth_seed"], CPMM_PROGRAM)[0]
SWAP_BASE_INPUT_DISCRIMINATOR = hashlib.sha256(b"global:swap_base_input").digest()[:8]
POOL_STATE_DISCRIMINATOR = hashlib.sha256(b"account:PoolState").digest()[:8]

# ExceededSlippage.
CPMM_SLIPPAGE_ERROR_CODES: set[int] = {6005}

FEE_RATE_DENOMINATOR = 1_000_000

# PoolState: discriminator, ten pubkeys, five u8 (auth_bump, status,
# lp_mint_decimals, mint_0_decimals, mint_1_decimals), seven u64 (lp_supply,
# protocol_fees_token_0/1, fund_fees_token_0/1, open_time, recent_epoch), two u8
# (creator_fee_on, enable_creator_fee), six bytes of padding, then the creator
# fees owed in each token.
_POOL_KEYS = (
    "amm_config",
    "pool_creator",
    "token_0_vault",
    "token_1_vault",
    "lp_mint",
    "token_0_mint",
    "token_1_mint",
    "token_0_program",
    "token_1_program",
    "observation_key",
)
_POOL_DECIMALS_OFFSET = 8 + 10 * 32 + 3
_POOL_FEES_OFFSET = 8 + 10 * 32 + 5 + 8
_POOL_CREATOR_FEE_FLAG_OFFSET = 8 + 10 * 32 + 5 + 7 * 8 + 1
_POOL_CREATOR_FEES_OFFSET = 8 + 10 * 32 + 5 + 7 * 8 + 2 + 6
# AmmConfig: discriminator, bump, disable_create_pool, index u16, trade_fee_rate,
# protocol, fund and create-pool fees, two owners, creator_fee_rate.
_CONFIG_TRADE_FEE_OFFSET = 8 + 1 + 1 + 2
_CONFIG_CREATOR_FEE_OFFSET = _CONFIG_TRADE_FEE_OFFSET + 4 * 8 + 2 * 32


def cpmm_pool_address(amm_config: Pubkey, mint_a: Pubkey, mint_b: Pubkey) -> Pubkey:
    """CPMM orders a pair's mints by their raw bytes before deriving the pool."""
    token_0, token_1 = sorted([mint_a, mint_b], key=bytes)
    return Pubkey.find_program_address(
        [b"pool", bytes(amm_config), bytes(token_0), bytes(token_1)], CPMM_PROGRAM
    )[0]


def parse_cpmm_pool(data: bytes, base_mint: Pubkey) -> dict:
    """Decode a PoolState, oriented so `base_*` is the coin and `quote_*` the other side.

    `base_fees` / `quote_fees` are what the vaults hold that is not liquidity:
    protocol, fund and creator fees not yet claimed.

    Raises:
        ValueError: If the data is not a PoolState or the pool doesn't trade `base_mint`
    """
    if len(data) < _POOL_CREATOR_FEES_OFFSET + 16 or data[:8] != POOL_STATE_DISCRIMINATOR:
        raise ValueError("Not a Raydium CPMM pool account")  # noqa: TRY003
    keys = {
        name: Pubkey.from_bytes(data[8 + 32 * i : 8 + 32 * (i + 1)])
        for i, name in enumerate(_POOL_KEYS)
    }
    if base_mint not in (keys["token_0_mint"], keys["token_1_mint"]):
        raise ValueError(f"CPMM pool does not trade {base_mint}")  # noqa: TRY003
    base = 0 if keys["token_0_mint"] == base_mint else 1
    quote = 1 - base
    p0, p1, f0, f1 = struct.unpack_from("<4Q", data, _POOL_FEES_OFFSET)
    c0, c1 = struct.unpack_from("<2Q", data, _POOL_CREATOR_FEES_OFFSET)
    fees = (p0 + f0 + c0, p1 + f1 + c1)
    decimals = data[_POOL_DECIMALS_OFFSET : _POOL_DECIMALS_OFFSET + 2]
    return {
        "amm_config": keys["amm_config"],
        "observation": keys["observation_key"],
        "base_mint": base_mint,
        "quote_mint": keys[f"token_{quote}_mint"],
        "base_vault": keys[f"token_{base}_vault"],
        "quote_vault": keys[f"token_{quote}_vault"],
        "base_token_program": keys[f"token_{base}_program"],
        "quote_token_program": keys[f"token_{quote}_program"],
        "base_decimals": decimals[base],
        "quote_decimals": decimals[quote],
        "base_fees": fees[base],
        "quote_fees": fees[quote],
        "creator_fee_enabled": bool(data[_POOL_CREATOR_FEE_FLAG_OFFSET]),
    }


def parse_cpmm_fee_rate(amm_config: bytes, creator_fee_enabled: bool) -> int:
    """Total swap fee in parts per million: the trade fee, plus the creator fee if on."""
    trade = struct.unpack_from("<Q", amm_config, _CONFIG_TRADE_FEE_OFFSET)[0]
    creator = struct.unpack_from("<Q", amm_config, _CONFIG_CREATOR_FEE_OFFSET)[0]
    return trade + (creator if creator_fee_enabled else 0)


def swap_amount_out(reserve_in: int, reserve_out: int, amount_in: int, fee_rate: int) -> int:
    """Constant-product output for `amount_in`, with the fee taken off the input.

    An estimate for sizing the slippage floor: the program may take the
    creator fee from either side.
    """
    net_in = amount_in - -(-amount_in * fee_rate // FEE_RATE_DENOMINATOR)
    return reserve_out * net_in // (reserve_in + net_in)


def build_cpmm_swap_instruction(
    *,
    buy: bool,
    pool_address: Pubkey,
    pool: dict,
    user: Pubkey,
    user_base_token: Pubkey,
    user_quote_token: Pubkey,
    amount_in: int,
    minimum_amount_out: int,
) -> Instruction:
    """swap_base_input of (amount_in, minimum_amount_out), input side first.

    The program reads the input token's account, vault, token program and mint
    before the output token's: a buy inputs the quote, a sell the coin.
    """
    base = (user_base_token, pool["base_vault"], pool["base_token_program"], pool["base_mint"])
    quote = (
        user_quote_token,
        pool["quote_vault"],
        pool["quote_token_program"],
        pool["quote_mint"],
    )
    (in_user, in_vault, in_program, in_mint), (out_user, out_vault, out_program, out_mint) = (
        (quote, base) if buy else (base, quote)
    )

    def meta(pubkey: Pubkey, writable: bool = False, signer: bool = False) -> AccountMeta:
        return AccountMeta(pubkey, is_signer=signer, is_writable=writable)

    accounts = [
        meta(user, writable=True, signer=True),
        meta(CPMM_AUTHORITY),
        meta(pool["amm_config"]),
        meta(pool_address, writable=True),
        meta(in_user, writable=True),
        meta(out_user, writable=True),
        meta(in_vault, writable=True),
        meta(out_vault, writable=True),
        meta(in_program),
        meta(out_program),
        meta(in_mint),
        meta(out_mint),
        meta(pool["observation"], writable=True),
    ]
    data = SWAP_BASE_INPUT_DISCRIMINATOR + struct.pack("<QQ", amount_in, minimum_amount_out)
    return Instruction(CPMM_PROGRAM, data, accounts)
