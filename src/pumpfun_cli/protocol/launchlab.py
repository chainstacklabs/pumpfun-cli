"""Raydium LaunchLab: addresses, account layouts, curve math and swap instructions.

LaunchLab is one program serving many launchpads (letsbonk.fun, StonkFun and
others); a launchpad is a set of platform configs its pools are created under.
Nothing here depends on which: every account a trade needs comes from the pool.

All amounts are raw integer units with the program's own rounding: fees round
up, curve outputs round down.
"""

import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import SYSTEM_PROGRAM

LAUNCHLAB_PROGRAM = Pubkey.from_string("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")

BUY_EXACT_IN_DISCRIMINATOR = bytes([250, 234, 13, 123, 213, 156, 19, 236])
SELL_EXACT_IN_DISCRIMINATOR = bytes([149, 39, 222, 155, 211, 124, 152, 26])
POOL_STATE_DISCRIMINATOR = bytes([247, 237, 227, 245, 215, 195, 222, 70])

# ExceededSlippage.
LAUNCHLAB_SLIPPAGE_ERROR_CODES: set[int] = {6004}

# A trade sends no front-end share fee.
SHARE_FEE_RATE = 0

# Fee rates on GlobalConfig and PlatformConfig are parts per million.
FEE_RATE_DENOMINATOR = 1_000_000
_BASIS_POINTS = 10_000

# PoolState: discriminator, epoch, five u8 (auth_bump, status, base_decimals,
# quote_decimals, migrate_type), ten u64 amounts, a five-u64 vesting schedule,
# then seven pubkeys from global_config on.
POOL_STATE_SIZE = 429
_POOL_U8_OFFSET = 16
_POOL_AMOUNTS_OFFSET = 21
_POOL_KEYS_OFFSET = 8 + 8 + 5 + 10 * 8 + 5 * 8
_POOL_KEYS = (
    "global_config",
    "platform_config",
    "base_mint",
    "quote_mint",
    "base_vault",
    "quote_vault",
    "creator",
)
POOL_BASE_MINT_OFFSET = _POOL_KEYS_OFFSET + 2 * 32

# GlobalConfig: discriminator, epoch u64, curve_type u8, index u16, migrate_fee u64.
_GLOBAL_CURVE_TYPE_OFFSET = 16
_GLOBAL_TRADE_FEE_RATE_OFFSET = 8 + 8 + 1 + 2 + 8
# The curve math here is for constant-product curves; LaunchLab also defines
# fixed-price (1) and linear (2) ones.
CONSTANT_PRODUCT_CURVE = 0
# PlatformConfig: discriminator, epoch, two wallets, three u64 scales, fee_rate,
# name[64], web[256], img[256], cpswap_config, creator_fee_rate.
_PLATFORM_FEE_RATE_OFFSET = 8 + 8 + 32 + 32 + 3 * 8
_PLATFORM_NAME_OFFSET = _PLATFORM_FEE_RATE_OFFSET + 8
PLATFORM_CPSWAP_CONFIG_OFFSET = _PLATFORM_NAME_OFFSET + 64 + 256 + 256
_PLATFORM_CREATOR_FEE_RATE_OFFSET = PLATFORM_CPSWAP_CONFIG_OFFSET + 32

# Token-2022 mint: 82-byte base mint, padding to 165, one account-type byte,
# then type-length-value extensions. TransferFeeConfig holds two authorities
# and a withheld amount (72 bytes), then the older and newer fees, each
# (epoch u64, maximum_fee u64, basis_points u16).
_EXTENSIONS_OFFSET = 166
_TRANSFER_FEE_CONFIG = 1
_OLDER_FEE_OFFSET = 72
_NEWER_FEE_OFFSET = 90

# Pool status: 0 trades on the curve, 1 waits for migration, 2 has migrated.
STATUS_TRADING = 0
# PoolState.migrate_type: 0 migrates to Raydium AMM v4, 1 to CPMM.
MIGRATE_TO_CPMM = 1


def _pda(*seeds: bytes) -> Pubkey:
    return Pubkey.find_program_address(list(seeds), LAUNCHLAB_PROGRAM)[0]


def derive_launchlab_pool(base_mint: Pubkey, quote_mint: Pubkey) -> Pubkey:
    """The pool for a base/quote pair."""
    return _pda(b"pool", bytes(base_mint), bytes(quote_mint))


def derive_launchlab_authority() -> Pubkey:
    """The PDA that signs for every pool vault."""
    return _pda(b"vault_auth_seed")


def derive_launchlab_event_authority() -> Pubkey:
    return _pda(b"__event_authority")


def derive_platform_fee_vault(platform_config: Pubkey, quote_mint: Pubkey) -> Pubkey:
    """Where a platform's share of curve fees accrues, per quote mint."""
    return _pda(bytes(platform_config), bytes(quote_mint))


def derive_creator_fee_vault(creator: Pubkey, quote_mint: Pubkey) -> Pubkey:
    """Where a creator's share of curve fees accrues, per quote mint."""
    return _pda(bytes(creator), bytes(quote_mint))


def parse_pool_state(data: bytes) -> dict:
    """Decode a PoolState account.

    Raises:
        ValueError: If the data is not a PoolState
    """
    if len(data) < POOL_STATE_SIZE or data[:8] != POOL_STATE_DISCRIMINATOR:
        raise ValueError("Not a LaunchLab pool account")  # noqa: TRY003
    status, base_decimals, quote_decimals, migrate_type = data[
        _POOL_U8_OFFSET + 1 : _POOL_U8_OFFSET + 5
    ]
    (
        supply,
        total_base_sell,
        virtual_base,
        virtual_quote,
        real_base,
        real_quote,
        total_quote_fund_raising,
    ) = struct.unpack_from("<7Q", data, _POOL_AMOUNTS_OFFSET)
    pool = {
        "status": status,
        "base_decimals": base_decimals,
        "quote_decimals": quote_decimals,
        "migrate_type": migrate_type,
        "supply": supply,
        "total_base_sell": total_base_sell,
        "virtual_base": virtual_base,
        "virtual_quote": virtual_quote,
        "real_base": real_base,
        "real_quote": real_quote,
        "total_quote_fund_raising": total_quote_fund_raising,
    }
    for i, name in enumerate(_POOL_KEYS):
        start = _POOL_KEYS_OFFSET + 32 * i
        pool[name] = Pubkey.from_bytes(data[start : start + 32])
    return pool


def curve_type(global_config: bytes) -> int:
    """GlobalConfig.curve_type: 0 constant product, 1 fixed price, 2 linear."""
    return global_config[_GLOBAL_CURVE_TYPE_OFFSET]


def parse_fee_rate(global_config: bytes, platform_config: bytes) -> int:
    """Total curve fee in parts per million: trade, platform and creator fees."""
    return (
        struct.unpack_from("<Q", global_config, _GLOBAL_TRADE_FEE_RATE_OFFSET)[0]
        + struct.unpack_from("<Q", platform_config, _PLATFORM_FEE_RATE_OFFSET)[0]
        + struct.unpack_from("<Q", platform_config, _PLATFORM_CREATOR_FEE_RATE_OFFSET)[0]
    )


def platform_name(platform_config: bytes) -> str:
    """The launchpad's name as its PlatformConfig stores it."""
    raw = platform_config[_PLATFORM_NAME_OFFSET : _PLATFORM_NAME_OFFSET + 64]
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


def mint_transfer_fee(mint_data: bytes) -> tuple[tuple[int, int], ...]:
    """A Token-2022 mint's scheduled transfer fees, each (basis points, maximum fee raw).

    Both the older and the newer fee: a change only applies two epochs after it
    is set, and `withheld_fee` charges whichever withholds more, so an amount is
    never overestimated without reading the epoch. Empty for a mint without
    the extension.
    """
    offset = _EXTENSIONS_OFFSET
    while offset + 4 <= len(mint_data):
        kind, length = struct.unpack_from("<HH", mint_data, offset)
        if kind == 0 and length == 0:
            break
        if kind == _TRANSFER_FEE_CONFIG:
            body = mint_data[offset + 4 : offset + 4 + length]
            _, older_max, older_bps = struct.unpack_from("<QQH", body, _OLDER_FEE_OFFSET)
            _, newer_max, newer_bps = struct.unpack_from("<QQH", body, _NEWER_FEE_OFFSET)
            return tuple(dict.fromkeys(((older_bps, older_max), (newer_bps, newer_max))))
        offset += 4 + length
    return ()


def transfer_fee_bps(fees: tuple[tuple[int, int], ...]) -> int:
    """The highest scheduled rate, for display."""
    return max((bps for bps, _ in fees), default=0)


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def withheld_fee(amount: int, fees: tuple[tuple[int, int], ...]) -> int:
    """What Token-2022 withholds from a transfer of `amount`: rounded up, capped,
    and the larger of the scheduled fees."""
    return max(
        (min(_ceil_div(amount * bps, _BASIS_POINTS), cap) for bps, cap in fees if bps),
        default=0,
    )


def _reserves(pool: dict) -> tuple[int, int]:
    """The (base, quote) reserves the curve trades against.

    The virtual reserves are fixed at launch; the real ones record every trade.
    """
    return pool["virtual_base"] - pool["real_base"], pool["virtual_quote"] + pool["real_quote"]


def spot_price(pool: dict) -> float:
    """Whole quote units per whole token at the current point on the curve."""
    base, quote = _reserves(pool)
    if base <= 0 or quote <= 0:
        return 0.0
    return (quote / 10 ** pool["quote_decimals"]) / (base / 10 ** pool["base_decimals"])


def buy_amount_out(
    pool: dict, amount_in: int, fee_rate: int, transfer_fee: tuple[tuple[int, int], ...] = ()
) -> int:
    """Raw tokens that reach the buyer for exactly `amount_in` raw quote.

    The curve fee comes off the input, the rest trades on the curve, and the
    coin's transfer fee is withheld on delivery.
    """
    net_in = amount_in - _ceil_div(amount_in * fee_rate, FEE_RATE_DENOMINATOR)
    base, quote = _reserves(pool)
    out = base * net_in // (quote + net_in)
    return out - withheld_fee(out, transfer_fee)


def sell_amount_out(
    pool: dict, amount_in: int, fee_rate: int, transfer_fee: tuple[tuple[int, int], ...] = ()
) -> int:
    """Raw quote paid for sending `amount_in` raw tokens.

    The transfer fee is withheld on the way into the pool, the curve trades on
    what arrives, and the curve fee comes off the quote.
    """
    arrived = amount_in - withheld_fee(amount_in, transfer_fee)
    base, quote = _reserves(pool)
    gross = quote * arrived // (base + arrived)
    return gross - _ceil_div(gross * fee_rate, FEE_RATE_DENOMINATOR)


def build_launchlab_swap_instruction(
    *,
    buy: bool,
    pool_address: Pubkey,
    pool: dict,
    user: Pubkey,
    user_base_token: Pubkey,
    user_quote_token: Pubkey,
    base_token_program: Pubkey,
    quote_token_program: Pubkey,
    amount_in: int,
    minimum_amount_out: int,
) -> Instruction:
    """buy_exact_in (spend exactly `amount_in` quote) or sell_exact_in.

    The IDL's 15 accounts, then three the program reads positionally: the
    system program and the platform and creator fee vaults.
    """
    quote_mint = pool["quote_mint"]

    def meta(pubkey: Pubkey, writable: bool = False, signer: bool = False) -> AccountMeta:
        return AccountMeta(pubkey, is_signer=signer, is_writable=writable)

    accounts = [
        meta(user, writable=True, signer=True),
        meta(derive_launchlab_authority()),
        meta(pool["global_config"]),
        meta(pool["platform_config"]),
        meta(pool_address, writable=True),
        meta(user_base_token, writable=True),
        meta(user_quote_token, writable=True),
        meta(pool["base_vault"], writable=True),
        meta(pool["quote_vault"], writable=True),
        meta(pool["base_mint"]),
        meta(quote_mint),
        meta(base_token_program),
        meta(quote_token_program),
        meta(derive_launchlab_event_authority()),
        meta(LAUNCHLAB_PROGRAM),
        meta(SYSTEM_PROGRAM),
        meta(derive_platform_fee_vault(pool["platform_config"], quote_mint), writable=True),
        meta(derive_creator_fee_vault(pool["creator"], quote_mint), writable=True),
    ]
    discriminator = BUY_EXACT_IN_DISCRIMINATOR if buy else SELL_EXACT_IN_DISCRIMINATOR
    data = discriminator + struct.pack("<QQQ", amount_in, minimum_amount_out, SHARE_FEE_RATE)
    return Instruction(LAUNCHLAB_PROGRAM, data, accounts)
