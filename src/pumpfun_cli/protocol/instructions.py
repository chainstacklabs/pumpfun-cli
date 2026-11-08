"""Instruction builders for the pump.fun and PumpSwap programs.

Bonding-curve trades use buy_v2 / buy_exact_quote_in_v2 / sell_v2: a fixed
account list, the same for every coin whatever its quote asset, mayhem or
cashback status. The IDL under-reports PumpSwap's swap accounts, so those
lists follow what the program reads on chain, documented at each builder.
"""

import secrets
import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountWithSeedParams, create_account_with_seed
from spl.token.instructions import (
    close_account,
    create_idempotent_associated_token_account,
    initialize_account,
)
from spl.token.models import CloseAccountParams, InitializeAccountParams

from pumpfun_cli.protocol.address import (
    derive_amm_boost_vault_authority,
    derive_amm_creator_vault,
    derive_amm_fee_config,
    derive_amm_global_volume_accumulator,
    derive_amm_lp_mint,
    derive_amm_pool,
    derive_amm_pool_v2,
    derive_amm_user_volume_accumulator,
    derive_bonding_curve,
    derive_creator_vault,
    derive_mayhem_state,
    derive_pool_authority,
    find_ata,
    find_fee_config,
    find_global_volume_accumulator,
    find_quote_control,
    find_sharing_config,
    find_user_volume_accumulator,
)
from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    ATA_RENT_LAMPORTS,
    BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR,
    BUY_V2_DISCRIMINATOR,
    BUYBACK_FEE_RECIPIENTS,
    CLAIM_CASHBACK_V2_DISCRIMINATOR,
    CLOSE_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR,
    COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
    COLLECT_CREATOR_FEE_V2_DISCRIMINATOR,
    CREATE_V2_DISCRIMINATOR,
    EXTEND_ACCOUNT_DISCRIMINATOR,
    MAYHEM_GLOBAL_PARAMS,
    MAYHEM_PROGRAM_ID,
    MAYHEM_SOL_VAULT,
    MIGRATE_V2_DISCRIMINATOR,
    NORMAL_FEE_RECIPIENTS,
    PUMP_AMM_PROGRAM,
    PUMP_EVENT_AUTHORITY,
    PUMP_FEE_PROGRAM,
    PUMP_GLOBAL,
    PUMP_MINT_AUTHORITY,
    PUMP_PROGRAM,
    PUMP_SWAP_EVENT_AUTHORITY,
    PUMP_SWAP_GLOBAL_CONFIG,
    PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR,
    PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR,
    PUMPSWAP_SELL_DISCRIMINATOR,
    RENT,
    RESERVED_FEE_RECIPIENTS,
    SELL_V2_DISCRIMINATOR,
    SYSTEM_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_ACCOUNT_SIZE,
    TOKEN_PROGRAM,
    WSOL_MINT,
)

# OptionBool(true) is a single-field struct: one 0x01 byte, not a tagged Option.
_TRACK_VOLUME = bytes([1])


def _meta(pubkey: Pubkey, writable: bool = False, signer: bool = False) -> AccountMeta:
    return AccountMeta(pubkey=pubkey, is_signer=signer, is_writable=writable)


# --- Quote settlement ---


def quote_settlement_account(
    user: Pubkey, quote_mint: Pubkey, quote_token_program: Pubkey, funding: int = 0
) -> tuple[Pubkey, list[Instruction], list[Instruction]]:
    """The account a PumpSwap trade pays from or into, with setup and teardown.

    Wrapped SOL goes through a throwaway account at a fresh seed, funded with
    `funding` lamports and closed in the same transaction, so whatever is left
    returns as SOL and any WSOL the wallet already holds is left alone. Any
    other quote asset uses the wallet's ATA, created if missing.

    Returns:
        (account, instructions before the trade, instructions after it)
    """
    if quote_mint != WSOL_MINT:
        ata = find_ata(user, quote_mint, quote_token_program)
        create = create_idempotent_associated_token_account(
            user, user, quote_mint, quote_token_program
        )
        return ata, [create], []

    seed = secrets.token_hex(16)
    account = Pubkey.create_with_seed(user, seed, TOKEN_PROGRAM)
    open_ixs = [
        create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=user,
                to_pubkey=account,
                base=user,
                seed=seed,
                lamports=funding + ATA_RENT_LAMPORTS,
                space=TOKEN_ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM,
            )
        ),
        initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM, account=account, mint=WSOL_MINT, owner=user
            )
        ),
    ]
    close_ixs = [
        close_account(
            CloseAccountParams(program_id=TOKEN_PROGRAM, account=account, dest=user, owner=user)
        )
    ]
    return account, open_ixs, close_ixs


# --- pump.fun bonding curve: v2 trades ---


def pick_fee_recipient(is_mayhem_mode: bool) -> Pubkey:
    """A fee recipient from the set the program expects for this coin."""
    return secrets.choice(RESERVED_FEE_RECIPIENTS if is_mayhem_mode else NORMAL_FEE_RECIPIENTS)


def build_v2_accounts(
    *,
    mint: Pubkey,
    creator: Pubkey,
    user: Pubkey,
    quote_mint: Pubkey,
    base_token_program: Pubkey,
    quote_token_program: Pubkey,
    is_mayhem_mode: bool,
    is_buy: bool,
) -> list[AccountMeta]:
    """The account list buy_v2, buy_exact_quote_in_v2 and sell_v2 share.

    27 accounts for a buy, 26 for a sell (no global_volume_accumulator). Every
    account is mandatory. For a SOL-paired coin `quote_mint` is wrapped SOL;
    the user's quote account is only seed-checked and must not be created.

    Args:
        creator: BondingCurve.creator as read from chain. On a holder-reward or
            fee-sharing coin it differs from whoever launched the coin, and the
            creator vault derives from it.
    """
    bonding_curve = derive_bonding_curve(mint)
    creator_vault = derive_creator_vault(creator)
    user_volume_accumulator = find_user_volume_accumulator(user)
    fee_recipient = pick_fee_recipient(is_mayhem_mode)
    buyback_recipient = secrets.choice(BUYBACK_FEE_RECIPIENTS)

    def quote_ata(owner: Pubkey) -> Pubkey:
        return find_ata(owner, quote_mint, quote_token_program)

    accounts = [
        _meta(PUMP_GLOBAL),
        _meta(mint),
        _meta(quote_mint),
        _meta(base_token_program),
        _meta(quote_token_program),
        _meta(ASSOCIATED_TOKEN_PROGRAM),
        _meta(fee_recipient, writable=True),
        _meta(quote_ata(fee_recipient), writable=True),
        _meta(buyback_recipient, writable=True),
        _meta(quote_ata(buyback_recipient), writable=True),
        _meta(bonding_curve, writable=True),
        _meta(find_ata(bonding_curve, mint, base_token_program), writable=True),
        _meta(quote_ata(bonding_curve), writable=True),
        _meta(user, writable=True, signer=True),
        _meta(find_ata(user, mint, base_token_program), writable=True),
        _meta(quote_ata(user), writable=True),
        _meta(creator_vault, writable=True),
        _meta(quote_ata(creator_vault), writable=True),
        _meta(find_sharing_config(mint)),
    ]
    if is_buy:
        accounts.append(_meta(find_global_volume_accumulator()))
    accounts += [
        _meta(user_volume_accumulator, writable=True),
        _meta(quote_ata(user_volume_accumulator), writable=True),
        _meta(find_fee_config()),
        _meta(PUMP_FEE_PROGRAM),
        _meta(SYSTEM_PROGRAM),
        _meta(PUMP_EVENT_AUTHORITY),
        _meta(PUMP_PROGRAM),
    ]
    return accounts


def build_buy_exact_quote_in_v2_instruction(
    *,
    mint: Pubkey,
    creator: Pubkey,
    user: Pubkey,
    spendable_quote_in: int,
    min_tokens_out: int,
    quote_mint: Pubkey = WSOL_MINT,
    base_token_program: Pubkey = TOKEN_2022_PROGRAM,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
    is_mayhem_mode: bool = False,
) -> Instruction:
    """Spend exactly `spendable_quote_in` (raw quote units, fees included), receive at least
    `min_tokens_out` raw tokens."""
    return Instruction(
        PUMP_PROGRAM,
        BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR
        + struct.pack("<QQ", spendable_quote_in, min_tokens_out),
        build_v2_accounts(
            mint=mint,
            creator=creator,
            user=user,
            quote_mint=quote_mint,
            base_token_program=base_token_program,
            quote_token_program=quote_token_program,
            is_mayhem_mode=is_mayhem_mode,
            is_buy=True,
        ),
    )


def build_buy_v2_instruction(
    *,
    mint: Pubkey,
    creator: Pubkey,
    user: Pubkey,
    token_amount: int,
    max_quote_cost: int,
    quote_mint: Pubkey = WSOL_MINT,
    base_token_program: Pubkey = TOKEN_2022_PROGRAM,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
    is_mayhem_mode: bool = False,
) -> Instruction:
    """Buy exactly `token_amount` raw tokens, spending at most `max_quote_cost` raw quote units."""
    return Instruction(
        PUMP_PROGRAM,
        BUY_V2_DISCRIMINATOR + struct.pack("<QQ", token_amount, max_quote_cost),
        build_v2_accounts(
            mint=mint,
            creator=creator,
            user=user,
            quote_mint=quote_mint,
            base_token_program=base_token_program,
            quote_token_program=quote_token_program,
            is_mayhem_mode=is_mayhem_mode,
            is_buy=True,
        ),
    )


def build_sell_v2_instruction(
    *,
    mint: Pubkey,
    creator: Pubkey,
    user: Pubkey,
    token_amount: int,
    min_quote_out: int,
    quote_mint: Pubkey = WSOL_MINT,
    base_token_program: Pubkey = TOKEN_2022_PROGRAM,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
    is_mayhem_mode: bool = False,
) -> Instruction:
    """Sell `token_amount` raw tokens for at least `min_quote_out` raw quote units."""
    return Instruction(
        PUMP_PROGRAM,
        SELL_V2_DISCRIMINATOR + struct.pack("<QQ", token_amount, min_quote_out),
        build_v2_accounts(
            mint=mint,
            creator=creator,
            user=user,
            quote_mint=quote_mint,
            base_token_program=base_token_program,
            quote_token_program=quote_token_program,
            is_mayhem_mode=is_mayhem_mode,
            is_buy=False,
        ),
    )


# --- pump.fun coin creation ---


def encode_create_v2_trailing_args(
    *, creator_fee_bps: int | None = None, is_holder_reward: bool | None = None
) -> bytes:
    """Encode create_v2's trailing args: is_cashback_enabled, creator_fee_bps, is_holder_reward.

    They are positional with no presence tag, so setting a later one sends the
    earlier ones too. None omits an arg. Cashback is always sent as false:
    create_v2 rejects true with 6082 (CashbackDeprecated).
    """
    if creator_fee_bps is None and is_holder_reward is None:
        return b""
    data = struct.pack("<?", False) + struct.pack("<Q", creator_fee_bps or 0)
    if is_holder_reward is not None:
        data += struct.pack("<?", is_holder_reward)
    return data


def build_create_v2_instruction(
    *,
    mint: Pubkey,
    user: Pubkey,
    creator: Pubkey,
    name: str,
    symbol: str,
    uri: str,
    is_mayhem_mode: bool = False,
    creator_fee_bps: int | None = None,
    is_holder_reward: bool | None = None,
    quote_mint: Pubkey = WSOL_MINT,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
) -> Instruction:
    """Build create_v2, which mints the coin under Token-2022.

    20 accounts: the IDL's 16, then quote_mint, the curve's quote account, the
    quote token program and QuoteControl as remaining accounts. They are sent
    for SOL-paired coins too; leaving them out lands a SOL coin and silently
    drops any creator fee.
    """
    bonding_curve = derive_bonding_curve(mint)
    accounts = [
        _meta(mint, writable=True, signer=True),
        _meta(PUMP_MINT_AUTHORITY),
        _meta(bonding_curve, writable=True),
        _meta(find_ata(bonding_curve, mint, TOKEN_2022_PROGRAM), writable=True),
        _meta(PUMP_GLOBAL),
        _meta(user, writable=True, signer=True),
        _meta(SYSTEM_PROGRAM),
        _meta(TOKEN_2022_PROGRAM),
        _meta(ASSOCIATED_TOKEN_PROGRAM),
        _meta(MAYHEM_PROGRAM_ID, writable=True),
        _meta(MAYHEM_GLOBAL_PARAMS),
        _meta(MAYHEM_SOL_VAULT, writable=True),
        _meta(derive_mayhem_state(mint), writable=True),
        _meta(find_ata(MAYHEM_SOL_VAULT, mint, TOKEN_2022_PROGRAM), writable=True),
        _meta(PUMP_EVENT_AUTHORITY),
        _meta(PUMP_PROGRAM),
        _meta(quote_mint),
        _meta(find_ata(bonding_curve, quote_mint, quote_token_program), writable=True),
        _meta(quote_token_program),
        _meta(find_quote_control()),
    ]

    def borsh_string(value: str) -> bytes:
        encoded = value.encode("utf-8")
        return struct.pack("<I", len(encoded)) + encoded

    data = (
        CREATE_V2_DISCRIMINATOR
        + borsh_string(name)
        + borsh_string(symbol)
        + borsh_string(uri)
        + bytes(creator)
        + struct.pack("<?", is_mayhem_mode)
        + encode_create_v2_trailing_args(
            creator_fee_bps=creator_fee_bps, is_holder_reward=is_holder_reward
        )
    )
    return Instruction(PUMP_PROGRAM, data, accounts)


def build_extend_account_instruction(bonding_curve: Pubkey, user: Pubkey) -> Instruction:
    """Grow the curve past the 125 bytes create_v2 allocates, as pump.fun's frontend expects."""
    return Instruction(
        PUMP_PROGRAM,
        EXTEND_ACCOUNT_DISCRIMINATOR,
        [
            _meta(bonding_curve, writable=True),
            _meta(user, writable=True, signer=True),
            _meta(SYSTEM_PROGRAM),
            _meta(PUMP_EVENT_AUTHORITY),
            _meta(PUMP_PROGRAM),
        ],
    )


# --- PumpSwap AMM ---


def _pumpswap_accounts(
    *,
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    tokens: dict,
    user_quote_account: Pubkey,
    fee_recipient: Pubkey,
    buyback_recipient: Pubkey,
    is_buy: bool,
) -> list[AccountMeta]:
    """PumpSwap's swap accounts: the IDL's list, then the extras the program reads.

    After the IDL's 23 (buy) or 21 (sell): the cashback account(s) on a
    cashback pool, `pool-v2` on a canonical pool only, and the buyback
    recipient with its quote account last. The program reads that pair from
    the end, so sending `pool-v2` on a non-canonical pool shifts it and the
    trade fails with 6053 (BuybackFeeRecipientNotAuthorized).
    """
    base_mint = pool["base_mint"]
    quote_mint = pool["quote_mint"]
    base_program = tokens["base_token_program"]
    quote_program = tokens["quote_token_program"]
    creator_vault = derive_amm_creator_vault(pool["coin_creator"])
    user_volume_accumulator = derive_amm_user_volume_accumulator(user)

    def quote_ata(owner: Pubkey) -> Pubkey:
        return find_ata(owner, quote_mint, quote_program)

    accounts = [
        _meta(pool_address, writable=True),
        _meta(user, writable=True, signer=True),
        _meta(PUMP_SWAP_GLOBAL_CONFIG),
        _meta(base_mint),
        _meta(quote_mint),
        _meta(find_ata(user, base_mint, base_program), writable=True),
        _meta(user_quote_account, writable=True),
        _meta(pool["pool_base_token_account"], writable=True),
        _meta(pool["pool_quote_token_account"], writable=True),
        _meta(fee_recipient),
        _meta(quote_ata(fee_recipient), writable=True),
        _meta(base_program),
        _meta(quote_program),
        _meta(SYSTEM_PROGRAM),
        _meta(ASSOCIATED_TOKEN_PROGRAM),
        _meta(PUMP_SWAP_EVENT_AUTHORITY),
        _meta(PUMP_AMM_PROGRAM),
        _meta(quote_ata(creator_vault), writable=True),
        _meta(creator_vault),
    ]
    if is_buy:
        accounts += [
            _meta(derive_amm_global_volume_accumulator()),
            _meta(user_volume_accumulator, writable=True),
        ]
    accounts += [_meta(derive_amm_fee_config()), _meta(PUMP_FEE_PROGRAM)]
    if pool["is_cashback_coin"]:
        accounts.append(_meta(quote_ata(user_volume_accumulator), writable=True))
        if not is_buy:
            accounts.append(_meta(user_volume_accumulator, writable=True))
    if pool["is_canonical"]:
        accounts.append(_meta(derive_amm_pool_v2(base_mint)))
    accounts += [_meta(buyback_recipient), _meta(quote_ata(buyback_recipient), writable=True)]
    return accounts


def build_pumpswap_buy_exact_quote_in_instructions(
    *,
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    tokens: dict,
    fee_recipient: Pubkey,
    buyback_recipient: Pubkey,
    spendable_quote_in: int,
    min_base_amount_out: int,
    wsol_funding: int = 0,
) -> list[Instruction]:
    """Spend exactly `spendable_quote_in` raw quote units on a PumpSwap pool.

    A SOL pool is paid from a throwaway WSOL account funded with `wsol_funding`
    lamports and closed afterwards, so unspent SOL comes straight back.
    """
    user_quote, open_ixs, close_ixs = quote_settlement_account(
        user, pool["quote_mint"], tokens["quote_token_program"], funding=wsol_funding
    )
    create_base_ata = create_idempotent_associated_token_account(
        user, user, pool["base_mint"], tokens["base_token_program"]
    )
    accounts = _pumpswap_accounts(
        user=user,
        pool_address=pool_address,
        pool=pool,
        tokens=tokens,
        user_quote_account=user_quote,
        fee_recipient=fee_recipient,
        buyback_recipient=buyback_recipient,
        is_buy=True,
    )
    data = (
        PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR
        + struct.pack("<QQ", spendable_quote_in, min_base_amount_out)
        + _TRACK_VOLUME
    )
    swap = Instruction(PUMP_AMM_PROGRAM, data, accounts)
    return [*open_ixs, create_base_ata, swap, *close_ixs]


def build_pumpswap_sell_instructions(
    *,
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    tokens: dict,
    fee_recipient: Pubkey,
    buyback_recipient: Pubkey,
    token_amount: int,
    min_quote_out: int,
) -> list[Instruction]:
    """Sell `token_amount` raw base tokens on a PumpSwap pool for at least `min_quote_out`."""
    user_quote, open_ixs, close_ixs = quote_settlement_account(
        user, pool["quote_mint"], tokens["quote_token_program"]
    )
    accounts = _pumpswap_accounts(
        user=user,
        pool_address=pool_address,
        pool=pool,
        tokens=tokens,
        user_quote_account=user_quote,
        fee_recipient=fee_recipient,
        buyback_recipient=buyback_recipient,
        is_buy=False,
    )
    data = PUMPSWAP_SELL_DISCRIMINATOR + struct.pack("<QQ", token_amount, min_quote_out)
    swap = Instruction(PUMP_AMM_PROGRAM, data, accounts)
    return [*open_ixs, swap, *close_ixs]


def build_init_amm_user_volume_accumulator(user: Pubkey) -> Instruction:
    """Build init_user_volume_accumulator instruction for PumpSwap AMM."""
    return Instruction(
        PUMP_AMM_PROGRAM,
        PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR,
        [
            _meta(user, writable=True, signer=True),
            _meta(user),
            _meta(derive_amm_user_volume_accumulator(user), writable=True),
            _meta(SYSTEM_PROGRAM),
            _meta(PUMP_SWAP_EVENT_AUTHORITY),
            _meta(PUMP_AMM_PROGRAM),
        ],
    )


# --- Payouts, cleanup and migration ---


def build_claim_cashback_v2_instruction(
    *, user: Pubkey, quote_mint: Pubkey = WSOL_MINT, quote_token_program: Pubkey = TOKEN_PROGRAM
) -> Instruction:
    """Pay out the cashback accrued on the user's volume accumulator in one quote asset."""
    accumulator = find_user_volume_accumulator(user)
    return Instruction(
        PUMP_PROGRAM,
        CLAIM_CASHBACK_V2_DISCRIMINATOR,
        [
            _meta(user, writable=True),
            _meta(accumulator, writable=True),
            _meta(quote_mint),
            _meta(quote_token_program),
            _meta(ASSOCIATED_TOKEN_PROGRAM),
            _meta(find_ata(accumulator, quote_mint, quote_token_program), writable=True),
            _meta(find_ata(user, quote_mint, quote_token_program), writable=True),
            _meta(SYSTEM_PROGRAM),
            _meta(PUMP_EVENT_AUTHORITY),
            _meta(PUMP_PROGRAM),
        ],
    )


def build_close_volume_accumulator_instruction(user: Pubkey) -> Instruction:
    """Build close_user_volume_accumulator instruction — recovers rent."""
    return Instruction(
        PUMP_PROGRAM,
        CLOSE_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR,
        [
            _meta(user, writable=True, signer=True),
            _meta(find_user_volume_accumulator(user), writable=True),
            _meta(PUMP_EVENT_AUTHORITY),
            _meta(PUMP_PROGRAM),
        ],
    )


def build_collect_creator_fee_v2_instruction(
    *,
    creator: Pubkey,
    quote_mint: Pubkey = WSOL_MINT,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
) -> Instruction:
    """Sweep a creator's pump.fun vault for one quote asset into the creator's wallet."""
    vault = derive_creator_vault(creator)
    return Instruction(
        PUMP_PROGRAM,
        COLLECT_CREATOR_FEE_V2_DISCRIMINATOR,
        [
            _meta(creator, writable=True),
            _meta(find_ata(creator, quote_mint, quote_token_program), writable=True),
            _meta(vault, writable=True),
            _meta(find_ata(vault, quote_mint, quote_token_program), writable=True),
            _meta(quote_mint),
            _meta(quote_token_program),
            _meta(ASSOCIATED_TOKEN_PROGRAM),
            _meta(SYSTEM_PROGRAM),
            _meta(PUMP_EVENT_AUTHORITY),
            _meta(PUMP_PROGRAM),
        ],
    )


def build_collect_coin_creator_fee_instruction(
    *,
    creator: Pubkey,
    quote_mint: Pubkey = WSOL_MINT,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
) -> Instruction:
    """Sweep a creator's PumpSwap vault for one quote asset into the creator's token account."""
    vault_authority = derive_amm_creator_vault(creator)
    return Instruction(
        PUMP_AMM_PROGRAM,
        COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
        [
            _meta(quote_mint),
            _meta(quote_token_program),
            _meta(creator),
            _meta(vault_authority),
            _meta(find_ata(vault_authority, quote_mint, quote_token_program), writable=True),
            _meta(find_ata(creator, quote_mint, quote_token_program), writable=True),
            _meta(PUMP_SWAP_EVENT_AUTHORITY),
            _meta(PUMP_AMM_PROGRAM),
        ],
    )


def build_migrate_v2_instruction(
    *,
    mint: Pubkey,
    user: Pubkey,
    withdraw_authority: Pubkey,
    quote_mint: Pubkey = WSOL_MINT,
    base_token_program: Pubkey = TOKEN_2022_PROGRAM,
    quote_token_program: Pubkey = TOKEN_PROGRAM,
) -> Instruction:
    """Move a complete curve's liquidity into its canonical PumpSwap pool.

    `withdraw_authority` is read from pump.fun's Global account. After the IDL's
    27 accounts come the new pool's boost vault authority and its quote token
    account: PumpSwap creates the boost vault during the migration.
    """
    bonding_curve = derive_bonding_curve(mint)
    pool_authority = derive_pool_authority(mint)
    pool = derive_amm_pool(mint, quote_mint)
    lp_mint = derive_amm_lp_mint(pool)
    boost_vault_authority = derive_amm_boost_vault_authority(pool)
    return Instruction(
        PUMP_PROGRAM,
        MIGRATE_V2_DISCRIMINATOR,
        [
            _meta(PUMP_GLOBAL),
            _meta(withdraw_authority, writable=True),
            _meta(mint),
            _meta(quote_mint),
            _meta(bonding_curve, writable=True),
            _meta(find_ata(bonding_curve, mint, base_token_program), writable=True),
            _meta(find_ata(bonding_curve, quote_mint, quote_token_program), writable=True),
            _meta(user, writable=True, signer=True),
            _meta(SYSTEM_PROGRAM),
            _meta(PUMP_AMM_PROGRAM),
            _meta(pool, writable=True),
            _meta(pool_authority, writable=True),
            _meta(find_ata(pool_authority, mint, base_token_program), writable=True),
            _meta(find_ata(pool_authority, quote_mint, quote_token_program), writable=True),
            _meta(PUMP_SWAP_GLOBAL_CONFIG),
            _meta(lp_mint, writable=True),
            _meta(find_ata(pool_authority, lp_mint, TOKEN_2022_PROGRAM), writable=True),
            _meta(find_ata(pool, mint, base_token_program), writable=True),
            _meta(find_ata(pool, quote_mint, quote_token_program), writable=True),
            _meta(base_token_program),
            _meta(quote_token_program),
            _meta(TOKEN_2022_PROGRAM),
            _meta(ASSOCIATED_TOKEN_PROGRAM),
            _meta(PUMP_SWAP_EVENT_AUTHORITY),
            _meta(RENT),
            _meta(PUMP_EVENT_AUTHORITY),
            _meta(PUMP_PROGRAM),
            _meta(boost_vault_authority),
            _meta(
                find_ata(boost_vault_authority, quote_mint, quote_token_program),
                writable=True,
            ),
        ],
    )
