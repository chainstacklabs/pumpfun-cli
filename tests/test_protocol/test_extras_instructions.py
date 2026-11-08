"""Payout, cleanup and migration builders follow the quote asset they act on."""

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_amm_boost_vault_authority,
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


def test_migrate_v2_appends_the_pools_boost_vault():
    keys = _keys(
        build_migrate_v2_instruction(
            mint=MINT,
            user=USER,
            withdraw_authority=Pubkey.new_unique(),
            quote_mint=QUOTE,
            quote_token_program=TOKEN_2022_PROGRAM,
        )
    )
    authority = derive_amm_boost_vault_authority(derive_amm_pool(MINT, QUOTE))
    assert keys[27:] == [authority, find_ata(authority, QUOTE, TOKEN_2022_PROGRAM)]


# A migrate_v2 that landed on mainnet (SOL-priced coin), account by account.
MAINNET_MIGRATE_V2 = [
    "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf",
    "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
    "AvgXW4hP7ozPe8P2VVnyEcCgfyKGotsKsKTzVhHSpump",
    "So11111111111111111111111111111111111111112",
    "4SxVXjWAVRJtiQz3c15jEvyMVchLnYypphtGwPo4Ue1p",
    "Gy7y5cqYHWujSgAkhqauMVuup1etnYBaZcd7EJwpTRSD",
    "27gKsZFVnG1dsrUEiqo7JeXNeihmWbLFhwKk5fxaK16Q",
    "9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5",
    "11111111111111111111111111111111",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
    "4nUaWTVN4tXficDXbDPBa1zkz22mMaKsSc9PcZVxkDLU",
    "Cq2HTwfL5atMtti6X5kGxu2tJcfHBfTBgPibEg3kSp1X",
    "EYjAvmPPvryzoEcUHg7tW3spfwvp8WyGhVdgNVAoh36i",
    "EscT6HjfPeMG7zrgPSrxP6EEdZPTVL61RrbdRQdTgS4x",
    "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw",
    "BHLrVmhAMT8SwM3pmwxboXaPmucPmG9F4SECdBEqsJRi",
    "CdEVwiDne4DgfYtZv8YzF5g8rnXsrRp8QXHh3RED5M48",
    "67vgDuzFqPZaCvRjgjBv1sHrPpn7i9WaVEinjeLXBKUr",
    "9Q3LxsWLB3rMzD3FibrMkn1KMrqRwe9dvM4vv9C9EvwB",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR",
    "SysvarRent111111111111111111111111111111111",
    "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "4jAkipqL5ESZJBau53Lwa8XMhtuRuvMPtSDXyEroxwC7",
    "3edD3kcShSfFwXYgeiWXhxNikatkKbbK2ww5thELSW8y",
]


def test_migrate_v2_matches_a_mainnet_migration():
    want = [Pubkey.from_string(k) for k in MAINNET_MIGRATE_V2]
    built = build_migrate_v2_instruction(mint=want[2], user=want[7], withdraw_authority=want[1])
    assert _keys(built) == want
    assert built.accounts[-1].is_writable and not built.accounts[-2].is_writable
