"""PDA derivation for pump.fun accounts."""

from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    MAYHEM_PROGRAM_ID,
    MAYHEM_SOL_VAULT,
    PUMP_AMM_PROGRAM,
    PUMP_EVENT_AUTHORITY,
    PUMP_FEE,
    PUMP_FEE_PROGRAM,
    PUMP_GLOBAL,
    PUMP_MAYHEM_FEE,
    PUMP_PROGRAM,
    SYSTEM_PROGRAM,
    TOKEN_2022_PROGRAM,
)


def derive_bonding_curve(mint: Pubkey) -> Pubkey:
    """Derive the bonding curve PDA for a token mint."""
    addr, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint)], PUMP_PROGRAM)
    return addr


def derive_bonding_curve_v2(mint: Pubkey) -> Pubkey:
    """Derive the bonding curve v2 PDA for a token mint."""
    addr, _ = Pubkey.find_program_address([b"bonding-curve-v2", bytes(mint)], PUMP_PROGRAM)
    return addr


def derive_associated_bonding_curve(
    mint: Pubkey,
    bonding_curve: Pubkey,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> Pubkey:
    """Derive the associated bonding curve (ATA of bonding curve for the token)."""
    addr, _ = Pubkey.find_program_address(
        [bytes(bonding_curve), bytes(token_program), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM,
    )
    return addr


def derive_creator_vault(creator: Pubkey) -> Pubkey:
    """Derive the creator vault PDA."""
    addr, _ = Pubkey.find_program_address([b"creator-vault", bytes(creator)], PUMP_PROGRAM)
    return addr


def find_global_volume_accumulator() -> Pubkey:
    """Derive the global volume accumulator PDA."""
    addr, _ = Pubkey.find_program_address([b"global_volume_accumulator"], PUMP_PROGRAM)
    return addr


def find_user_volume_accumulator(user: Pubkey) -> Pubkey:
    """Derive a user's volume accumulator PDA."""
    addr, _ = Pubkey.find_program_address([b"user_volume_accumulator", bytes(user)], PUMP_PROGRAM)
    return addr


def derive_mayhem_state(mint: Pubkey) -> Pubkey:
    """Derive the mayhem state PDA for a token mint."""
    addr, _ = Pubkey.find_program_address([b"mayhem-state", bytes(mint)], MAYHEM_PROGRAM_ID)
    return addr


def derive_mayhem_token_vault(mint: Pubkey) -> Pubkey:
    """Derive the mayhem token vault (ATA of SOL_VAULT for the mint)."""
    return get_associated_token_address(MAYHEM_SOL_VAULT, mint, TOKEN_2022_PROGRAM)


def find_fee_config() -> Pubkey:
    """Derive the fee config PDA."""
    addr, _ = Pubkey.find_program_address([b"fee_config", bytes(PUMP_PROGRAM)], PUMP_FEE_PROGRAM)
    return addr


def get_fee_recipient(is_mayhem_mode: bool) -> Pubkey:
    """Return the correct fee recipient based on mayhem mode."""
    return PUMP_MAYHEM_FEE if is_mayhem_mode else PUMP_FEE


def get_buy_accounts(
    mint: Pubkey,
    bonding_curve: Pubkey,
    assoc_bc: Pubkey,
    user: Pubkey,
    creator: Pubkey,
    is_mayhem: bool,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> dict[str, Pubkey]:
    """Return ordered account dict for buy instruction (16 base + 1 remaining)."""
    user_ata = get_associated_token_address(user, mint, token_program)
    return {
        "global": PUMP_GLOBAL,
        "fee": get_fee_recipient(is_mayhem),
        "mint": mint,
        "bonding_curve": bonding_curve,
        "associated_bonding_curve": assoc_bc,
        "user_token_account": user_ata,
        "user": user,
        "system_program": SYSTEM_PROGRAM,
        "token_program": token_program,
        "creator_vault": derive_creator_vault(creator),
        "event_authority": PUMP_EVENT_AUTHORITY,
        "program": PUMP_PROGRAM,
        "global_volume_accumulator": find_global_volume_accumulator(),
        "user_volume_accumulator": find_user_volume_accumulator(user),
        "fee_config": find_fee_config(),
        "fee_program": PUMP_FEE_PROGRAM,
        "bonding_curve_v2": derive_bonding_curve_v2(mint),
    }


def get_sell_accounts(
    mint: Pubkey,
    bonding_curve: Pubkey,
    assoc_bc: Pubkey,
    user: Pubkey,
    creator: Pubkey,
    is_mayhem: bool,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> dict[str, Pubkey]:
    """Return ordered account dict for sell instruction (14 base + remaining)."""
    user_ata = get_associated_token_address(user, mint, token_program)
    return {
        "global": PUMP_GLOBAL,
        "fee": get_fee_recipient(is_mayhem),
        "mint": mint,
        "bonding_curve": bonding_curve,
        "associated_bonding_curve": assoc_bc,
        "user_token_account": user_ata,
        "user": user,
        "system_program": SYSTEM_PROGRAM,
        "creator_vault": derive_creator_vault(creator),
        "token_program": token_program,
        "event_authority": PUMP_EVENT_AUTHORITY,
        "program": PUMP_PROGRAM,
        "fee_config": find_fee_config(),
        "fee_program": PUMP_FEE_PROGRAM,
        "user_volume_accumulator": find_user_volume_accumulator(user),
        "bonding_curve_v2": derive_bonding_curve_v2(mint),
    }


# --- PumpSwap AMM PDA derivation ---


def derive_amm_creator_vault(coin_creator: Pubkey) -> Pubkey:
    """Derive the PumpSwap creator vault PDA."""
    addr, _ = Pubkey.find_program_address(
        [b"creator_vault", bytes(coin_creator)], PUMP_AMM_PROGRAM
    )
    return addr


def derive_amm_fee_config() -> Pubkey:
    """Derive the PumpSwap fee config PDA."""
    addr, _ = Pubkey.find_program_address(
        [b"fee_config", bytes(PUMP_AMM_PROGRAM)], PUMP_FEE_PROGRAM
    )
    return addr


def derive_amm_global_volume_accumulator() -> Pubkey:
    """Derive the PumpSwap global volume accumulator PDA."""
    addr, _ = Pubkey.find_program_address([b"global_volume_accumulator"], PUMP_AMM_PROGRAM)
    return addr


def derive_amm_user_volume_accumulator(user: Pubkey) -> Pubkey:
    """Derive a user's PumpSwap volume accumulator PDA."""
    addr, _ = Pubkey.find_program_address(
        [b"user_volume_accumulator", bytes(user)], PUMP_AMM_PROGRAM
    )
    return addr


def derive_amm_pool_v2(base_mint: Pubkey) -> Pubkey:
    """Derive the PumpSwap pool-v2 PDA for a base mint."""
    addr, _ = Pubkey.find_program_address([b"pool-v2", bytes(base_mint)], PUMP_AMM_PROGRAM)
    return addr
