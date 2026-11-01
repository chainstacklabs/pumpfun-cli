"""Payout, cleanup and migration builders follow the quote asset they act on."""

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_amm_creator_vault,
    derive_amm_lp_mint,
    derive_amm_pool,
    derive_creator_vault,
    find_ata,
    find_user_volume_accumulator,
)
from pumpfun_cli.protocol.contracts import (
    RENT,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.instructions import (
    build_claim_cashback_v2_instruction,
    build_collect_coin_creator_fee_instruction,
    build_collect_creator_fee_v2_instruction,
    build_migrate_v2_instruction,
)

USER = Pubkey.new_unique()
MINT = Pubkey.new_unique()
QUOTE = Pubkey.new_unique()


def _keys(ix):
    return [m.pubkey for m in ix.accounts]


def test_claim_cashback_v2_uses_the_accumulators_quote_account():
    keys = _keys(
        build_claim_cashback_v2_instruction(
            user=USER, quote_mint=QUOTE, quote_token_program=TOKEN_2022_PROGRAM
        )
    )
    acc = find_user_volume_accumulator(USER)
    assert keys[2:4] == [QUOTE, TOKEN_2022_PROGRAM]
    assert keys[5] == find_ata(acc, QUOTE, TOKEN_2022_PROGRAM)
    assert keys[6] == find_ata(USER, QUOTE, TOKEN_2022_PROGRAM)


def test_collect_creator_fee_v2_per_quote_vault():
    keys = _keys(
        build_collect_creator_fee_v2_instruction(
            creator=USER, quote_mint=QUOTE, quote_token_program=TOKEN_2022_PROGRAM
        )
    )
    vault = derive_creator_vault(USER)
    assert keys[1] == find_ata(USER, QUOTE, TOKEN_2022_PROGRAM)
    assert keys[2] == vault
    assert keys[3] == find_ata(vault, QUOTE, TOKEN_2022_PROGRAM)


def test_collect_coin_creator_fee_defaults_to_wsol():
    keys = _keys(build_collect_coin_creator_fee_instruction(creator=USER))
    authority = derive_amm_creator_vault(USER)
    assert keys[0:2] == [WSOL_MINT, TOKEN_PROGRAM]
    assert keys[4] == find_ata(authority, WSOL_MINT, TOKEN_PROGRAM)
    assert keys[5] == find_ata(USER, WSOL_MINT, TOKEN_PROGRAM)


def test_migrate_v2_targets_the_quote_specific_pool():
    keys = _keys(
        build_migrate_v2_instruction(
            mint=MINT,
            user=USER,
            withdraw_authority=Pubkey.new_unique(),
            quote_mint=QUOTE,
            quote_token_program=TOKEN_2022_PROGRAM,
        )
    )
    pool = derive_amm_pool(MINT, QUOTE)
    assert keys[3] == QUOTE
    assert keys[10] == pool
    assert keys[15] == derive_amm_lp_mint(pool)
    assert keys[18] == find_ata(pool, QUOTE, TOKEN_2022_PROGRAM)
    assert keys[24] == RENT
