"""PumpSwap swap builders: the IDL prefix plus the accounts the program reads beyond it."""

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_amm_pool_v2,
    derive_amm_user_volume_accumulator,
    find_ata,
)
from pumpfun_cli.protocol.contracts import (
    PUMP_AMM_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.instructions import (
    build_pumpswap_buy_exact_quote_in_instructions,
    build_pumpswap_sell_instructions,
)
from tests.test_protocol.test_instructions import AMM_IDL, assert_matches_idl

USER = Pubkey.new_unique()
FEE = Pubkey.new_unique()
BUYBACK = Pubkey.new_unique()
TOKENS = {"base_token_program": TOKEN_2022_PROGRAM, "quote_token_program": TOKEN_PROGRAM}


def _pool(*, canonical=True, cashback=False, quote=WSOL_MINT):
    return {
        "base_mint": Pubkey.new_unique(),
        "quote_mint": quote,
        "pool_base_token_account": Pubkey.new_unique(),
        "pool_quote_token_account": Pubkey.new_unique(),
        "coin_creator": Pubkey.new_unique() if canonical else Pubkey.default(),
        "is_canonical": canonical,
        "is_cashback_coin": cashback,
        "is_mayhem_mode": False,
    }


def _swap(ixs):
    return next(i for i in ixs if i.program_id == PUMP_AMM_PROGRAM)


def _buy(pool, tokens=TOKENS, funding=1_000):
    return build_pumpswap_buy_exact_quote_in_instructions(
        user=USER,
        pool_address=Pubkey.new_unique(),
        pool=pool,
        tokens=tokens,
        fee_recipient=FEE,
        buyback_recipient=BUYBACK,
        spendable_quote_in=1_000,
        min_base_amount_out=1,
        wsol_funding=funding,
    )


def _sell(pool, tokens=TOKENS):
    return build_pumpswap_sell_instructions(
        user=USER,
        pool_address=Pubkey.new_unique(),
        pool=pool,
        tokens=tokens,
        fee_recipient=FEE,
        buyback_recipient=BUYBACK,
        token_amount=1,
        min_quote_out=1,
    )


@pytest.mark.parametrize(
    "canonical,cashback,buy_count,sell_count",
    [(True, False, 26, 24), (True, True, 27, 26), (False, False, 25, 23), (False, True, 26, 25)],
)
def test_swap_account_counts(canonical, cashback, buy_count, sell_count):
    pool = _pool(canonical=canonical, cashback=cashback)
    buy, sell = _swap(_buy(pool)), _swap(_sell(pool))
    assert len(buy.accounts) == buy_count
    assert len(sell.accounts) == sell_count
    assert_matches_idl(AMM_IDL, "buy_exact_quote_in", buy, prefix=23)
    assert_matches_idl(AMM_IDL, "sell", sell, prefix=21)


@pytest.mark.parametrize("canonical", [True, False])
def test_buyback_pair_is_last_and_pool_v2_only_on_canonical(canonical):
    pool = _pool(canonical=canonical)
    for swap in (_swap(_buy(pool)), _swap(_sell(pool))):
        keys = [m.pubkey for m in swap.accounts]
        assert keys[-2] == BUYBACK
        assert not swap.accounts[-2].is_writable
        assert keys[-1] == find_ata(BUYBACK, WSOL_MINT, TOKEN_PROGRAM)
        assert swap.accounts[-1].is_writable
        assert (derive_amm_pool_v2(pool["base_mint"]) in keys) == canonical


def test_cashback_accounts_precede_pool_v2():
    pool = _pool(cashback=True)
    acc = derive_amm_user_volume_accumulator(USER)
    acc_quote = find_ata(acc, WSOL_MINT, TOKEN_PROGRAM)
    buy = [m.pubkey for m in _swap(_buy(pool)).accounts]
    sell = [m.pubkey for m in _swap(_sell(pool)).accounts]
    assert buy[23] == acc_quote and buy[24] == derive_amm_pool_v2(pool["base_mint"])
    assert sell[21:23] == [acc_quote, acc]


def test_sol_buy_wraps_through_a_closed_throwaway_account():
    ixs = _buy(_pool(), funding=5_000)
    swap = _swap(ixs)
    user_quote = swap.accounts[6].pubkey
    assert user_quote != find_ata(USER, WSOL_MINT, TOKEN_PROGRAM)
    # create-with-seed, initialize, create base ATA, swap, close
    assert len(ixs) == 5
    assert ixs[-1].program_id == TOKEN_PROGRAM
    assert user_quote in [m.pubkey for m in ixs[-1].accounts]


def test_non_sol_pool_settles_through_the_wallet_ata():
    quote = Pubkey.new_unique()
    tokens = {"base_token_program": TOKEN_2022_PROGRAM, "quote_token_program": TOKEN_2022_PROGRAM}
    pool = _pool(quote=quote)
    swap = _swap(_sell(pool, tokens))
    assert swap.accounts[6].pubkey == find_ata(USER, quote, TOKEN_2022_PROGRAM)
    assert swap.accounts[12].pubkey == TOKEN_2022_PROGRAM
    assert swap.accounts[-1].pubkey == find_ata(BUYBACK, quote, TOKEN_2022_PROGRAM)
