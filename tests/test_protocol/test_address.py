"""PDA derivations that no builder test reaches through an IDL seed spec."""

from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from pumpfun_cli.protocol.address import (
    derive_amm_pool,
    derive_pool_authority,
    find_ata,
    find_holder_rewards,
    find_quote_control,
)
from pumpfun_cli.protocol.contracts import (
    PUMP_AMM_PROGRAM,
    PUMP_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    USDC_MINT,
    WSOL_MINT,
)

MINT = Pubkey.new_unique()
OWNER = Pubkey.new_unique()


def test_find_ata_matches_spl_for_both_token_programs():
    for program in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
        assert find_ata(OWNER, MINT, program) == get_associated_token_address(OWNER, MINT, program)
    assert find_ata(OWNER, MINT, TOKEN_PROGRAM) != find_ata(OWNER, MINT, TOKEN_2022_PROGRAM)


def test_canonical_pool_depends_on_quote_mint():
    authority = derive_pool_authority(MINT)
    expected = Pubkey.find_program_address(
        [b"pool", bytes([0, 0]), bytes(authority), bytes(MINT), bytes(USDC_MINT)],
        PUMP_AMM_PROGRAM,
    )[0]
    assert derive_amm_pool(MINT, USDC_MINT) == expected
    assert derive_amm_pool(MINT) == derive_amm_pool(MINT, WSOL_MINT) != expected


def test_holder_rewards_and_quote_control_seeds():
    assert (
        find_holder_rewards(MINT)
        == Pubkey.find_program_address([b"holder-rewards", bytes(MINT)], PUMP_PROGRAM)[0]
    )
    assert find_quote_control() == Pubkey.find_program_address([b"quote-control"], PUMP_PROGRAM)[0]
