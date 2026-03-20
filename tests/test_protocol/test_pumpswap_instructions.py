"""Tests for PumpSwap instruction builders."""

from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from pumpfun_cli.protocol.contracts import (
    PUMP_AMM_PROGRAM,
    PUMPSWAP_BUY_DISCRIMINATOR,
    PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR,
    PUMPSWAP_SELL_DISCRIMINATOR,
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.instructions import (
    build_pumpswap_buy_exact_quote_in_instructions,
    build_pumpswap_buy_instructions,
    build_pumpswap_sell_instructions,
)

_USER = Pubkey.from_string("11111111111111111111111111111112")
_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
_POOL = Pubkey.from_string("11111111111111111111111111111113")
_FEE_RECIPIENT_ATA = get_associated_token_address(
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    WSOL_MINT,
    TOKEN_PROGRAM,
)

_POOL_DATA = {
    "base_mint": _MINT,
    "quote_mint": WSOL_MINT,
    "pool_base_token_account": Pubkey.from_string("11111111111111111111111111111114"),
    "pool_quote_token_account": Pubkey.from_string("11111111111111111111111111111115"),
    "coin_creator": _USER,
}


def test_pumpswap_buy_returns_five_instructions():
    ixs = build_pumpswap_buy_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        amount_out=1_000_000,
        max_sol_in=100_000_000,
        sol_wrap_lamports=110_000_000,
    )
    assert len(ixs) == 5


def test_pumpswap_buy_last_ix_has_24_accounts():
    ixs = build_pumpswap_buy_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        amount_out=1_000_000,
        max_sol_in=100_000_000,
        sol_wrap_lamports=110_000_000,
    )
    buy_ix = ixs[-1]
    assert len(buy_ix.accounts) == 24
    assert buy_ix.program_id == PUMP_AMM_PROGRAM
    assert buy_ix.data[:8] == PUMPSWAP_BUY_DISCRIMINATOR


def test_pumpswap_sell_returns_two_instructions():
    ixs = build_pumpswap_sell_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        token_amount=1_000_000,
        min_sol_out=0,
    )
    assert len(ixs) == 2


def test_pumpswap_sell_last_ix_has_21_accounts():
    ixs = build_pumpswap_sell_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        token_amount=1_000_000,
        min_sol_out=0,
    )
    sell_ix = ixs[-1]
    assert len(sell_ix.accounts) == 22
    assert sell_ix.program_id == PUMP_AMM_PROGRAM
    assert sell_ix.data[:8] == PUMPSWAP_SELL_DISCRIMINATOR


def test_pumpswap_buy_first_account_is_pool():
    ixs = build_pumpswap_buy_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        amount_out=1_000_000,
        max_sol_in=100_000_000,
        sol_wrap_lamports=110_000_000,
    )
    buy_ix = ixs[-1]
    assert buy_ix.accounts[0].pubkey == _POOL
    assert buy_ix.accounts[0].is_writable is True


def test_pumpswap_sell_first_account_is_pool():
    ixs = build_pumpswap_sell_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        token_amount=1_000_000,
        min_sol_out=0,
    )
    sell_ix = ixs[-1]
    assert sell_ix.accounts[0].pubkey == _POOL
    assert sell_ix.accounts[0].is_writable is True


def test_pumpswap_buy_exact_quote_in_returns_five():
    ixs = build_pumpswap_buy_exact_quote_in_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        spendable_quote_in=100_000_000,
        min_base_amount_out=1_000_000,
        sol_wrap_lamports=110_000_000,
    )
    assert len(ixs) == 5


def test_pumpswap_buy_exact_quote_in_discriminator():
    ixs = build_pumpswap_buy_exact_quote_in_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        spendable_quote_in=100_000_000,
        min_base_amount_out=1_000_000,
        sol_wrap_lamports=110_000_000,
    )
    buy_ix = ixs[-1]
    assert buy_ix.data[:8] == PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR
    assert len(buy_ix.accounts) == 24


def test_pumpswap_buy_data_has_track_volume():
    """PumpSwap buy instruction data should be 25 bytes: 8 disc + 8 + 8 + 1 OptionBool."""
    ixs = build_pumpswap_buy_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        amount_out=1_000_000,
        max_sol_in=100_000_000,
        sol_wrap_lamports=110_000_000,
    )
    buy_ix = ixs[-1]
    data = bytes(buy_ix.data)
    assert len(data) == 25  # 8 + 8 + 8 + 1
    assert data[-1:] == bytes([1])


def test_pumpswap_buy_exact_quote_in_data_has_track_volume():
    """PumpSwap buy_exact_quote_in data should be 25 bytes with trailing OptionBool."""
    ixs = build_pumpswap_buy_exact_quote_in_instructions(
        user=_USER,
        pool_address=_POOL,
        pool=_POOL_DATA,
        token_program_id=TOKEN_PROGRAM,
        fee_recipient=STANDARD_PUMPSWAP_FEE_RECIPIENT,
        fee_recipient_ata=_FEE_RECIPIENT_ATA,
        spendable_quote_in=100_000_000,
        min_base_amount_out=1_000_000,
        sol_wrap_lamports=110_000_000,
    )
    buy_ix = ixs[-1]
    data = bytes(buy_ix.data)
    assert len(data) == 25
    assert data[-1:] == bytes([1])
