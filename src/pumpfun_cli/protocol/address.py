"""PDA derivation for pump.fun and PumpSwap accounts."""

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    MAYHEM_PROGRAM_ID,
    MAYHEM_SOL_VAULT,
    PUMP_AMM_PROGRAM,
    PUMP_FEE_PROGRAM,
    PUMP_PROGRAM,
    TOKEN_2022_PROGRAM,
    WSOL_MINT,
)


def find_ata(owner: Pubkey, mint: Pubkey, token_program: Pubkey) -> Pubkey:
    """Associated token account; the address depends on which program owns the mint."""
    addr, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(token_program), bytes(mint)], ASSOCIATED_TOKEN_PROGRAM
    )
    return addr


def derive_bonding_curve(mint: Pubkey) -> Pubkey:
    """Derive the bonding curve PDA for a token mint."""
    addr, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint)], PUMP_PROGRAM)
    return addr


def derive_associated_bonding_curve(
    mint: Pubkey,
    bonding_curve: Pubkey,
    token_program: Pubkey = TOKEN_2022_PROGRAM,
) -> Pubkey:
    """The bonding curve's token account for the coin."""
    return find_ata(bonding_curve, mint, token_program)


def derive_creator_vault(creator: Pubkey) -> Pubkey:
    """Derive the pump.fun creator vault PDA from BondingCurve.creator."""
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
    return find_ata(MAYHEM_SOL_VAULT, mint, TOKEN_2022_PROGRAM)


def find_fee_config() -> Pubkey:
    """Derive the pump.fun fee config PDA (under the pump fees program)."""
    addr, _ = Pubkey.find_program_address([b"fee_config", bytes(PUMP_PROGRAM)], PUMP_FEE_PROGRAM)
    return addr


def find_sharing_config(mint: Pubkey) -> Pubkey:
    """Derive the creator-fee sharing config PDA (under the pump fees program)."""
    addr, _ = Pubkey.find_program_address([b"sharing-config", bytes(mint)], PUMP_FEE_PROGRAM)
    return addr


def find_holder_rewards(mint: Pubkey) -> Pubkey:
    """The PDA a holder-reward coin carries as BondingCurve.creator instead of its creator."""
    addr, _ = Pubkey.find_program_address([b"holder-rewards", bytes(mint)], PUMP_PROGRAM)
    return addr


def find_quote_control() -> Pubkey:
    """Derive the QuoteControl PDA, the registry of admitted quote mints."""
    addr, _ = Pubkey.find_program_address([b"quote-control"], PUMP_PROGRAM)
    return addr


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


def derive_pool_authority(mint: Pubkey) -> Pubkey:
    """Derive the pool authority PDA used during migration."""
    addr, _ = Pubkey.find_program_address([b"pool-authority", bytes(mint)], PUMP_PROGRAM)
    return addr


def derive_amm_pool(mint: Pubkey, quote_mint: Pubkey = WSOL_MINT) -> Pubkey:
    """Derive the canonical PumpSwap pool a pump.fun curve migrates into.

    Seeds: ["pool", u16 0, pool_authority, base_mint, quote_mint]. The quote mint
    is the curve's, so a coin priced in USDC graduates into a USDC pool.
    """
    pool_authority = derive_pool_authority(mint)
    addr, _ = Pubkey.find_program_address(
        [b"pool", bytes([0, 0]), bytes(pool_authority), bytes(mint), bytes(quote_mint)],
        PUMP_AMM_PROGRAM,
    )
    return addr


def derive_amm_lp_mint(pool: Pubkey) -> Pubkey:
    """Derive a PumpSwap pool's LP mint."""
    addr, _ = Pubkey.find_program_address([b"pool_lp_mint", bytes(pool)], PUMP_AMM_PROGRAM)
    return addr
