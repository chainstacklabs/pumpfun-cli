"""Build buy/sell/create instructions for the pump.fun program."""

import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from spl.token.instructions import (
    create_idempotent_associated_token_account,
    get_associated_token_address,
)

from pumpfun_cli.protocol.address import (
    derive_amm_creator_vault,
    derive_amm_fee_config,
    derive_amm_global_volume_accumulator,
    derive_amm_pool_v2,
    derive_amm_user_volume_accumulator,
    get_buy_accounts,
    get_sell_accounts,
)
from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    MAYHEM_GLOBAL_PARAMS,
    MAYHEM_PROGRAM_ID,
    MAYHEM_SOL_VAULT,
    PUMP_AMM_PROGRAM,
    PUMP_EVENT_AUTHORITY,
    PUMP_FEE_PROGRAM,
    PUMP_GLOBAL,
    PUMP_PROGRAM,
    PUMP_SWAP_EVENT_AUTHORITY,
    PUMP_SWAP_GLOBAL_CONFIG,
    PUMPSWAP_BUY_DISCRIMINATOR,
    PUMPSWAP_SELL_DISCRIMINATOR,
    SYSTEM_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.idl_parser import IDLParser

# Trailing bytes appended after the two u64 args (track_volume flag).
_TRACK_VOLUME = bytes([1, 1])


def build_buy_instructions(
    idl: IDLParser,
    mint: Pubkey,
    user: Pubkey,
    bonding_curve: Pubkey,
    assoc_bc: Pubkey,
    creator: Pubkey,
    is_mayhem: bool,
    token_amount: int,
    max_sol_cost: int,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> list[Instruction]:
    """Build the ATA-creation + buy instructions for a pump.fun token.

    Returns a list of two instructions:
    1. Idempotent ATA creation for the user's token account.
    2. The buy instruction with 16 base accounts + bonding_curve_v2.
    """
    # --- ATA creation instruction ---
    ata_ix = create_idempotent_associated_token_account(
        payer=user, owner=user, mint=mint, token_program_id=token_program
    )

    # --- Buy instruction ---
    accounts = get_buy_accounts(
        mint=mint,
        bonding_curve=bonding_curve,
        assoc_bc=assoc_bc,
        user=user,
        creator=creator,
        is_mayhem=is_mayhem,
        token_program=token_program,
    )

    buy_accounts = [
        AccountMeta(pubkey=accounts["global"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["bonding_curve"], is_signer=False, is_writable=True),
        AccountMeta(
            pubkey=accounts["associated_bonding_curve"], is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=accounts["user_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["user"], is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts["system_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["token_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["creator_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["event_authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["program"], is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=accounts["global_volume_accumulator"], is_signer=False, is_writable=False
        ),
        AccountMeta(pubkey=accounts["user_volume_accumulator"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["fee_config"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["bonding_curve_v2"], is_signer=False, is_writable=False),
    ]

    discriminators = idl.get_instruction_discriminators()
    instruction_data = (
        discriminators["buy"]
        + struct.pack("<Q", token_amount)
        + struct.pack("<Q", max_sol_cost)
        + _TRACK_VOLUME
    )

    buy_ix = Instruction(
        program_id=PUMP_PROGRAM,
        accounts=buy_accounts,
        data=instruction_data,
    )

    return [ata_ix, buy_ix]


def build_buy_exact_sol_in_instructions(
    idl: IDLParser,
    mint: Pubkey,
    user: Pubkey,
    bonding_curve: Pubkey,
    assoc_bc: Pubkey,
    creator: Pubkey,
    is_mayhem: bool,
    spendable_sol_in: int,
    min_tokens_out: int,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> list[Instruction]:
    """Build ATA-creation + buy_exact_sol_in instructions.

    Same accounts as buy, different discriminator and arg semantics:
    - spendable_sol_in: exact SOL budget (fees deducted from this)
    - min_tokens_out: minimum tokens to receive (slippage protection)
    """
    from pumpfun_cli.protocol.contracts import BUY_EXACT_SOL_IN_DISCRIMINATOR

    ata_ix = create_idempotent_associated_token_account(
        payer=user, owner=user, mint=mint, token_program_id=token_program
    )

    accounts = get_buy_accounts(
        mint=mint,
        bonding_curve=bonding_curve,
        assoc_bc=assoc_bc,
        user=user,
        creator=creator,
        is_mayhem=is_mayhem,
        token_program=token_program,
    )

    buy_accounts = [
        AccountMeta(pubkey=accounts["global"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["bonding_curve"], is_signer=False, is_writable=True),
        AccountMeta(
            pubkey=accounts["associated_bonding_curve"], is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=accounts["user_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["user"], is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts["system_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["token_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["creator_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["event_authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["program"], is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=accounts["global_volume_accumulator"], is_signer=False, is_writable=False
        ),
        AccountMeta(pubkey=accounts["user_volume_accumulator"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["fee_config"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["bonding_curve_v2"], is_signer=False, is_writable=False),
    ]

    instruction_data = (
        BUY_EXACT_SOL_IN_DISCRIMINATOR
        + struct.pack("<Q", spendable_sol_in)
        + struct.pack("<Q", min_tokens_out)
        + _TRACK_VOLUME
    )

    buy_ix = Instruction(
        program_id=PUMP_PROGRAM,
        accounts=buy_accounts,
        data=instruction_data,
    )

    return [ata_ix, buy_ix]


def build_sell_instructions(
    idl: IDLParser,
    mint: Pubkey,
    user: Pubkey,
    bonding_curve: Pubkey,
    assoc_bc: Pubkey,
    creator: Pubkey,
    is_mayhem: bool,
    token_amount: int,
    min_sol_output: int,
    is_cashback: bool = False,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> list[Instruction]:
    """Build the sell instruction for a pump.fun token.

    Returns a list containing a single sell instruction with 14 base accounts
    plus remaining accounts (user_volume_accumulator for cashback, bonding_curve_v2 always).
    """
    accounts = get_sell_accounts(
        mint=mint,
        bonding_curve=bonding_curve,
        assoc_bc=assoc_bc,
        user=user,
        creator=creator,
        is_mayhem=is_mayhem,
        token_program=token_program,
    )

    sell_accounts = [
        AccountMeta(pubkey=accounts["global"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["bonding_curve"], is_signer=False, is_writable=True),
        AccountMeta(
            pubkey=accounts["associated_bonding_curve"], is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=accounts["user_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["user"], is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts["system_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["creator_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["token_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["event_authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee_config"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["fee_program"], is_signer=False, is_writable=False),
    ]

    if is_cashback:
        sell_accounts.append(
            AccountMeta(
                pubkey=accounts["user_volume_accumulator"], is_signer=False, is_writable=True
            ),
        )
    sell_accounts.append(
        AccountMeta(pubkey=accounts["bonding_curve_v2"], is_signer=False, is_writable=False),
    )

    discriminators = idl.get_instruction_discriminators()
    instruction_data = (
        discriminators["sell"]
        + struct.pack("<Q", token_amount)
        + struct.pack("<Q", min_sol_output)
        + _TRACK_VOLUME
    )

    sell_ix = Instruction(
        program_id=PUMP_PROGRAM,
        accounts=sell_accounts,
        data=instruction_data,
    )

    return [sell_ix]


def _derive_mint_authority() -> Pubkey:
    """Derive the pump.fun mint authority PDA."""
    addr, _ = Pubkey.find_program_address([b"mint-authority"], PUMP_PROGRAM)
    return addr


def _encode_borsh_string(s: str) -> bytes:
    """Borsh string encoding: 4-byte LE length prefix + UTF-8 bytes."""
    encoded = s.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def build_create_instructions(
    idl: IDLParser,
    mint: Pubkey,
    user: Pubkey,
    name: str,
    symbol: str,
    uri: str,
    is_mayhem: bool = False,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> list[Instruction]:
    """Build create_v2 token instruction for pump.fun (Token2022).

    The create_v2 instruction initialises a new token mint with Token-2022,
    bonding curve, and optionally mayhem state.  It requires two signers:
    the wallet (user/payer) and the freshly generated mint keypair.

    Account order follows the IDL ``create_v2`` instruction definition.
    """
    from pumpfun_cli.protocol.address import (
        derive_associated_bonding_curve,
        derive_bonding_curve,
        derive_mayhem_state,
        derive_mayhem_token_vault,
    )

    bonding_curve = derive_bonding_curve(mint)
    assoc_bc = derive_associated_bonding_curve(mint, bonding_curve, token_program)
    mint_auth = _derive_mint_authority()

    create_accounts = [
        AccountMeta(pubkey=mint, is_signer=True, is_writable=True),
        AccountMeta(pubkey=mint_auth, is_signer=False, is_writable=False),
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(pubkey=assoc_bc, is_signer=False, is_writable=True),
        AccountMeta(pubkey=PUMP_GLOBAL, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_2022_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM, is_signer=False, is_writable=False),
    ]

    if is_mayhem:
        mayhem_state = derive_mayhem_state(mint)
        mayhem_token_vault = derive_mayhem_token_vault(mint)
        create_accounts.extend(
            [
                AccountMeta(pubkey=MAYHEM_PROGRAM_ID, is_signer=False, is_writable=True),
                AccountMeta(pubkey=MAYHEM_GLOBAL_PARAMS, is_signer=False, is_writable=False),
                AccountMeta(pubkey=MAYHEM_SOL_VAULT, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mayhem_state, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mayhem_token_vault, is_signer=False, is_writable=True),
            ]
        )

    create_accounts.extend(
        [
            AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
            AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
        ]
    )

    discriminators = idl.get_instruction_discriminators()

    instruction_data = (
        discriminators["create_v2"]
        + _encode_borsh_string(name)
        + _encode_borsh_string(symbol)
        + _encode_borsh_string(uri)
        + bytes(user)  # creator arg
        + struct.pack("<?", is_mayhem)  # is_mayhem_mode: bool
    )

    create_ix = Instruction(
        program_id=PUMP_PROGRAM,
        accounts=create_accounts,
        data=instruction_data,
    )

    return [create_ix]


def build_extend_account_instruction(
    idl: IDLParser,
    bonding_curve: Pubkey,
    user: Pubkey,
) -> Instruction:
    """Build extend_account instruction to expand bonding curve account size.

    Required after create_v2 for frontend visibility.
    """
    accounts = [
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    discriminators = idl.get_instruction_discriminators()
    return Instruction(
        program_id=PUMP_PROGRAM,
        accounts=accounts,
        data=discriminators["extend_account"],
    )


# --- PumpSwap AMM instruction builders ---


def build_pumpswap_buy_instructions(
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    token_program_id: Pubkey,
    fee_recipient: Pubkey,
    fee_recipient_ata: Pubkey,
    amount_out: int,
    max_sol_in: int,
    sol_wrap_lamports: int,
) -> list[Instruction]:
    """Build PumpSwap buy instructions (WSOL wrap + buy swap).

    Returns 5 instructions:
    1. Create WSOL ATA (idempotent)
    2. Transfer SOL to WSOL ATA
    3. Sync native
    4. Create base token ATA (idempotent)
    5. Buy instruction (23 IDL accounts + 2 trailing: vol_wsol_ata, pool_v2)
    """
    from solders.system_program import TransferParams, transfer
    from spl.token.instructions import SyncNativeParams, sync_native

    user_wsol_ata = get_associated_token_address(user, WSOL_MINT, TOKEN_PROGRAM)
    user_token_ata = get_associated_token_address(user, pool["base_mint"], token_program_id)

    coin_creator = pool["coin_creator"]
    creator_vault_authority = derive_amm_creator_vault(coin_creator)
    creator_vault_ata = get_associated_token_address(
        creator_vault_authority, WSOL_MINT, TOKEN_PROGRAM
    )

    # 1. Create WSOL ATA
    create_wsol_ata = create_idempotent_associated_token_account(
        payer=user,
        owner=user,
        mint=WSOL_MINT,
        token_program_id=TOKEN_PROGRAM,
    )

    # 2. Transfer SOL to WSOL ATA
    transfer_ix = transfer(
        TransferParams(
            from_pubkey=user,
            to_pubkey=user_wsol_ata,
            lamports=sol_wrap_lamports,
        )
    )

    # 3. Sync native
    sync_ix = sync_native(
        SyncNativeParams(
            program_id=TOKEN_PROGRAM,
            account=user_wsol_ata,
        )
    )

    # 4. Create base token ATA
    create_token_ata = create_idempotent_associated_token_account(
        payer=user,
        owner=user,
        mint=pool["base_mint"],
        token_program_id=token_program_id,
    )

    # 5. Buy instruction (24 accounts: 17 IDL + 6 remaining + pool_v2 trailing)
    pool_v2 = derive_amm_pool_v2(pool["base_mint"])

    buy_accounts = [
        AccountMeta(pubkey=pool_address, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=PUMP_SWAP_GLOBAL_CONFIG, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool["base_mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=WSOL_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user_token_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user_wsol_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_base_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_quote_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=fee_recipient, is_signer=False, is_writable=False),
        AccountMeta(pubkey=fee_recipient_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_AMM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator_vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=creator_vault_authority, is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=derive_amm_global_volume_accumulator(), is_signer=False, is_writable=False
        ),
        AccountMeta(
            pubkey=derive_amm_user_volume_accumulator(user), is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=derive_amm_fee_config(), is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_FEE_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool_v2, is_signer=False, is_writable=False),
    ]

    instruction_data = (
        PUMPSWAP_BUY_DISCRIMINATOR + struct.pack("<Q", amount_out) + struct.pack("<Q", max_sol_in)
    )

    buy_ix = Instruction(
        program_id=PUMP_AMM_PROGRAM,
        accounts=buy_accounts,
        data=instruction_data,
    )

    return [create_wsol_ata, transfer_ix, sync_ix, create_token_ata, buy_ix]


def build_pumpswap_buy_exact_quote_in_instructions(
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    token_program_id: Pubkey,
    fee_recipient: Pubkey,
    fee_recipient_ata: Pubkey,
    spendable_quote_in: int,
    min_base_amount_out: int,
    sol_wrap_lamports: int,
) -> list[Instruction]:
    """Build PumpSwap buy_exact_quote_in instructions (WSOL wrap + buy swap).

    Same 5 instructions and 23 accounts as regular buy, but uses
    buy_exact_quote_in discriminator with (spendable_quote_in, min_base_amount_out) args.
    """
    from solders.system_program import TransferParams, transfer
    from spl.token.instructions import SyncNativeParams, sync_native

    from pumpfun_cli.protocol.contracts import PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR

    user_wsol_ata = get_associated_token_address(user, WSOL_MINT, TOKEN_PROGRAM)
    user_token_ata = get_associated_token_address(user, pool["base_mint"], token_program_id)

    coin_creator = pool["coin_creator"]
    creator_vault_authority = derive_amm_creator_vault(coin_creator)
    creator_vault_ata = get_associated_token_address(
        creator_vault_authority, WSOL_MINT, TOKEN_PROGRAM
    )

    create_wsol_ata = create_idempotent_associated_token_account(
        payer=user,
        owner=user,
        mint=WSOL_MINT,
        token_program_id=TOKEN_PROGRAM,
    )
    transfer_ix = transfer(
        TransferParams(
            from_pubkey=user,
            to_pubkey=user_wsol_ata,
            lamports=sol_wrap_lamports,
        )
    )
    sync_ix = sync_native(
        SyncNativeParams(
            program_id=TOKEN_PROGRAM,
            account=user_wsol_ata,
        )
    )
    create_token_ata = create_idempotent_associated_token_account(
        payer=user,
        owner=user,
        mint=pool["base_mint"],
        token_program_id=token_program_id,
    )

    pool_v2 = derive_amm_pool_v2(pool["base_mint"])

    buy_accounts = [
        AccountMeta(pubkey=pool_address, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=PUMP_SWAP_GLOBAL_CONFIG, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool["base_mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=WSOL_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user_token_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user_wsol_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_base_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_quote_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=fee_recipient, is_signer=False, is_writable=False),
        AccountMeta(pubkey=fee_recipient_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_AMM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator_vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=creator_vault_authority, is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=derive_amm_global_volume_accumulator(), is_signer=False, is_writable=False
        ),
        AccountMeta(
            pubkey=derive_amm_user_volume_accumulator(user), is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=derive_amm_fee_config(), is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_FEE_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool_v2, is_signer=False, is_writable=False),
    ]

    instruction_data = (
        PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR
        + struct.pack("<Q", spendable_quote_in)
        + struct.pack("<Q", min_base_amount_out)
    )

    buy_ix = Instruction(
        program_id=PUMP_AMM_PROGRAM,
        accounts=buy_accounts,
        data=instruction_data,
    )

    return [create_wsol_ata, transfer_ix, sync_ix, create_token_ata, buy_ix]


def build_init_amm_user_volume_accumulator(user: Pubkey) -> Instruction:
    """Build init_user_volume_accumulator instruction for PumpSwap AMM."""
    INIT_DISCRIMINATOR = bytes([94, 6, 202, 115, 255, 96, 232, 183])
    user_vol = derive_amm_user_volume_accumulator(user)
    accounts = [
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=user, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user_vol, is_signer=False, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_AMM_PROGRAM, is_signer=False, is_writable=False),
    ]
    return Instruction(program_id=PUMP_AMM_PROGRAM, accounts=accounts, data=INIT_DISCRIMINATOR)


def build_pumpswap_sell_instructions(
    user: Pubkey,
    pool_address: Pubkey,
    pool: dict,
    token_program_id: Pubkey,
    fee_recipient: Pubkey,
    fee_recipient_ata: Pubkey,
    token_amount: int,
    min_sol_out: int,
) -> list[Instruction]:
    """Build PumpSwap sell instructions (WSOL ATA + sell swap).

    Returns 2 instructions:
    1. Create WSOL ATA (idempotent) - needed to receive SOL
    2. Sell instruction (21 IDL accounts + 1 trailing: pool_v2)
    """
    user_wsol_ata = get_associated_token_address(user, WSOL_MINT, TOKEN_PROGRAM)
    user_token_ata = get_associated_token_address(user, pool["base_mint"], token_program_id)

    coin_creator = pool["coin_creator"]
    creator_vault_authority = derive_amm_creator_vault(coin_creator)
    creator_vault_ata = get_associated_token_address(
        creator_vault_authority, WSOL_MINT, TOKEN_PROGRAM
    )

    # 1. Create WSOL ATA
    create_wsol_ata = create_idempotent_associated_token_account(
        payer=user,
        owner=user,
        mint=WSOL_MINT,
        token_program_id=TOKEN_PROGRAM,
    )

    # 2. Sell instruction (22 accounts: 17 IDL + 4 remaining + pool_v2 trailing)
    pool_v2 = derive_amm_pool_v2(pool["base_mint"])

    sell_accounts = [
        AccountMeta(pubkey=pool_address, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=PUMP_SWAP_GLOBAL_CONFIG, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool["base_mint"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=WSOL_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user_token_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user_wsol_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_base_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool["pool_quote_token_account"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=fee_recipient, is_signer=False, is_writable=False),
        AccountMeta(pubkey=fee_recipient_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_AMM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator_vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=creator_vault_authority, is_signer=False, is_writable=False),
        AccountMeta(pubkey=derive_amm_fee_config(), is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_FEE_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool_v2, is_signer=False, is_writable=False),
    ]

    instruction_data = (
        PUMPSWAP_SELL_DISCRIMINATOR
        + struct.pack("<Q", token_amount)
        + struct.pack("<Q", min_sol_out)
        # No track_volume arg — PumpSwap sell IDL only takes (base_amount_in, min_quote_amount_out)
    )

    sell_ix = Instruction(
        program_id=PUMP_AMM_PROGRAM,
        accounts=sell_accounts,
        data=instruction_data,
    )

    return [create_wsol_ata, sell_ix]


# --- Bonding curve extras & migration instruction builders ---


def build_claim_cashback_instruction(
    idl: IDLParser,
    user: Pubkey,
) -> Instruction:
    """Build claim_cashback instruction — claims volume-based cashback rewards."""
    from pumpfun_cli.protocol.address import find_user_volume_accumulator

    accounts = [
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=find_user_volume_accumulator(user), is_signer=False, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    discriminators = idl.get_instruction_discriminators()
    return Instruction(
        program_id=PUMP_PROGRAM,
        accounts=accounts,
        data=discriminators["claim_cashback"],
    )


def build_close_volume_accumulator_instruction(
    idl: IDLParser,
    user: Pubkey,
) -> Instruction:
    """Build close_user_volume_accumulator instruction — recovers rent."""
    from pumpfun_cli.protocol.address import find_user_volume_accumulator

    accounts = [
        AccountMeta(pubkey=user, is_signer=True, is_writable=True),
        AccountMeta(pubkey=find_user_volume_accumulator(user), is_signer=False, is_writable=True),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    discriminators = idl.get_instruction_discriminators()
    return Instruction(
        program_id=PUMP_PROGRAM,
        accounts=accounts,
        data=discriminators["close_user_volume_accumulator"],
    )


def _derive_migrate_pool_authority(mint: Pubkey) -> Pubkey:
    """Derive the pool authority PDA for migration."""
    addr, _ = Pubkey.find_program_address([b"pool-authority", bytes(mint)], PUMP_PROGRAM)
    return addr


def build_migrate_instruction(
    idl: IDLParser,
    mint: Pubkey,
    user: Pubkey,
    withdraw_authority: Pubkey,
) -> Instruction:
    """Build migrate instruction — triggers graduation from bonding curve to PumpSwap AMM.

    Requires 24 accounts. The withdraw_authority must be read from the Global account on-chain.
    """
    from pumpfun_cli.protocol.address import (
        derive_associated_bonding_curve,
        derive_bonding_curve,
    )

    bonding_curve = derive_bonding_curve(mint)
    assoc_bc = derive_associated_bonding_curve(mint, bonding_curve, TOKEN_2022_PROGRAM)
    pool_authority = _derive_migrate_pool_authority(mint)

    # Derive pool PDA on AMM program: seeds = [b"pool", [0,0], pool_authority, mint, wsol_mint]
    pool, _ = Pubkey.find_program_address(
        [b"pool", bytes([0, 0]), bytes(pool_authority), bytes(mint), bytes(WSOL_MINT)],
        PUMP_AMM_PROGRAM,
    )

    # LP mint PDA on AMM program: seeds = [b"pool_lp_mint", pool]
    lp_mint, _ = Pubkey.find_program_address([b"pool_lp_mint", bytes(pool)], PUMP_AMM_PROGRAM)

    # ATAs
    pool_authority_mint_account = get_associated_token_address(
        pool_authority,
        mint,
        TOKEN_2022_PROGRAM,
    )
    pool_authority_wsol_account = get_associated_token_address(
        pool_authority,
        WSOL_MINT,
        TOKEN_PROGRAM,
    )
    user_pool_token_account = get_associated_token_address(
        pool_authority,
        lp_mint,
        TOKEN_2022_PROGRAM,
    )
    pool_base_token_account = get_associated_token_address(
        pool,
        mint,
        TOKEN_2022_PROGRAM,
    )
    pool_quote_token_account = get_associated_token_address(
        pool,
        WSOL_MINT,
        TOKEN_PROGRAM,
    )

    accounts = [
        AccountMeta(pubkey=PUMP_GLOBAL, is_signer=False, is_writable=False),
        AccountMeta(pubkey=withdraw_authority, is_signer=False, is_writable=True),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(pubkey=assoc_bc, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user, is_signer=True, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_AMM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=pool, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_authority, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_authority_mint_account, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_authority_wsol_account, is_signer=False, is_writable=True),
        AccountMeta(pubkey=PUMP_SWAP_GLOBAL_CONFIG, is_signer=False, is_writable=False),
        AccountMeta(pubkey=WSOL_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=lp_mint, is_signer=False, is_writable=True),
        AccountMeta(pubkey=user_pool_token_account, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_base_token_account, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_quote_token_account, is_signer=False, is_writable=True),
        AccountMeta(pubkey=TOKEN_2022_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    discriminators = idl.get_instruction_discriminators()
    return Instruction(
        program_id=PUMP_PROGRAM,
        accounts=accounts,
        data=discriminators["migrate"],
    )


def build_collect_creator_fee_instruction(
    idl: "IDLParser",
    creator: Pubkey,
) -> Instruction:
    """Build collect_creator_fee instruction — collects fees from pump.fun creator vault."""
    from pumpfun_cli.protocol.address import derive_creator_vault
    from pumpfun_cli.protocol.contracts import COLLECT_CREATOR_FEE_DISCRIMINATOR

    accounts = [
        AccountMeta(pubkey=creator, is_signer=False, is_writable=True),
        AccountMeta(pubkey=derive_creator_vault(creator), is_signer=False, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    return Instruction(
        program_id=PUMP_PROGRAM,
        accounts=accounts,
        data=COLLECT_CREATOR_FEE_DISCRIMINATOR,
    )


def build_collect_coin_creator_fee_instruction(
    creator: Pubkey,
) -> Instruction:
    """Build collect_coin_creator_fee instruction — collects fees from PumpSwap creator vault."""
    from pumpfun_cli.protocol.address import derive_amm_creator_vault
    from pumpfun_cli.protocol.contracts import (
        COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
        WSOL_MINT,
    )

    creator_vault_authority = derive_amm_creator_vault(creator)
    creator_vault_ata = get_associated_token_address(
        creator_vault_authority, WSOL_MINT, TOKEN_PROGRAM
    )
    creator_wsol_ata = get_associated_token_address(creator, WSOL_MINT, TOKEN_PROGRAM)

    accounts = [
        AccountMeta(pubkey=WSOL_MINT, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator_vault_authority, is_signer=False, is_writable=False),
        AccountMeta(pubkey=creator_vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=creator_wsol_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=PUMP_SWAP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
    ]

    return Instruction(
        program_id=PUMP_AMM_PROGRAM,
        accounts=accounts,
        data=COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
    )
