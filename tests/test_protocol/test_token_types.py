"""Tests for all pump.fun token type combinations.

Covers the full matrix: Token-2022 vs SPL, mayhem vs standard,
cashback vs non-cashback, bonding curve vs PumpSwap, and instruction
account counts/fee routing for each combination.

Ref: docs/token-types-test-matrix.md
"""

from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_associated_bonding_curve,
    derive_bonding_curve,
)
from pumpfun_cli.protocol.contracts import (
    PUMP_FEE,
    PUMP_MAYHEM_FEE,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_sol_in_instructions,
    build_buy_instructions,
    build_sell_instructions,
)

IDL_PATH = Path(__file__).parent.parent.parent / "idl" / "pump_fun_idl.json"
_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
_USER = Pubkey.from_string("11111111111111111111111111111112")
_CREATOR = Pubkey.from_string("11111111111111111111111111111113")
_BC = derive_bonding_curve(_MINT)


# BC-BUY: Bonding curve buy — all token type combinations


class TestBondingCurveBuyTokenTypes:
    """BC-BUY-1 through BC-BUY-5: buy instruction account counts and fee routing."""

    def _build_buy(self, *, is_mayhem: bool, token_program: Pubkey):
        idl = IDLParser(str(IDL_PATH))
        abc = derive_associated_bonding_curve(_MINT, _BC, token_program)
        return build_buy_instructions(
            idl=idl,
            mint=_MINT,
            user=_USER,
            bonding_curve=_BC,
            assoc_bc=abc,
            creator=_CREATOR,
            is_mayhem=is_mayhem,
            token_amount=1_000_000,
            max_sol_cost=100_000_000,
            token_program=token_program,
        )

    def _get_fee_recipient(self, ixs):
        """Fee recipient is account index 1 (second account) of the buy ix."""
        buy_ix = ixs[-1]  # last ix is the buy
        return buy_ix.accounts[1].pubkey

    def _get_token_program_account(self, ixs):
        """Token program is account index 8 of the buy ix."""
        buy_ix = ixs[-1]
        return buy_ix.accounts[8].pubkey

    def test_bc_buy_1_standard_token2022(self):
        """BC-BUY-1: Standard Token-2022, no mayhem — 17 accounts, fee → PUMP_FEE."""
        ixs = self._build_buy(is_mayhem=False, token_program=TOKEN_2022_PROGRAM)
        assert len(ixs) == 2  # ATA creation + buy
        buy_ix = ixs[-1]
        assert len(buy_ix.accounts) == 17
        assert self._get_fee_recipient(ixs) == PUMP_FEE
        assert self._get_token_program_account(ixs) == TOKEN_2022_PROGRAM

    def test_bc_buy_2_mayhem_token(self):
        """BC-BUY-2: Mayhem Token-2022 — 17 accounts, fee → PUMP_MAYHEM_FEE."""
        ixs = self._build_buy(is_mayhem=True, token_program=TOKEN_2022_PROGRAM)
        buy_ix = ixs[-1]
        assert len(buy_ix.accounts) == 17
        assert self._get_fee_recipient(ixs) == PUMP_MAYHEM_FEE

    def test_bc_buy_5_legacy_spl_token(self):
        """BC-BUY-5: Legacy SPL Token — 17 accounts, token_program = TOKEN_PROGRAM."""
        ixs = self._build_buy(is_mayhem=False, token_program=TOKEN_PROGRAM)
        buy_ix = ixs[-1]
        assert len(buy_ix.accounts) == 17
        assert self._get_fee_recipient(ixs) == PUMP_FEE
        assert self._get_token_program_account(ixs) == TOKEN_PROGRAM

    def test_bc_buy_exact_sol_in_token2022(self):
        """buy_exact_sol_in also produces 17 accounts with correct fee routing."""
        idl = IDLParser(str(IDL_PATH))
        abc = derive_associated_bonding_curve(_MINT, _BC, TOKEN_2022_PROGRAM)
        ixs = build_buy_exact_sol_in_instructions(
            idl=idl,
            mint=_MINT,
            user=_USER,
            bonding_curve=_BC,
            assoc_bc=abc,
            creator=_CREATOR,
            is_mayhem=False,
            spendable_sol_in=10_000_000,
            min_tokens_out=1_000,
            token_program=TOKEN_2022_PROGRAM,
        )
        buy_ix = ixs[-1]
        assert len(buy_ix.accounts) == 17
        assert buy_ix.accounts[1].pubkey == PUMP_FEE

    def test_bc_buy_exact_sol_in_mayhem(self):
        """buy_exact_sol_in with mayhem routes fee to PUMP_MAYHEM_FEE."""
        idl = IDLParser(str(IDL_PATH))
        abc = derive_associated_bonding_curve(_MINT, _BC, TOKEN_2022_PROGRAM)
        ixs = build_buy_exact_sol_in_instructions(
            idl=idl,
            mint=_MINT,
            user=_USER,
            bonding_curve=_BC,
            assoc_bc=abc,
            creator=_CREATOR,
            is_mayhem=True,
            spendable_sol_in=10_000_000,
            min_tokens_out=1_000,
            token_program=TOKEN_2022_PROGRAM,
        )
        assert ixs[-1].accounts[1].pubkey == PUMP_MAYHEM_FEE


# BC-SELL: Bonding curve sell — cashback and non-cashback


class TestBondingCurveSellTokenTypes:
    """BC-SELL-1 through BC-SELL-5: sell account counts vary by cashback flag."""

    def _build_sell(
        self,
        *,
        is_mayhem: bool,
        is_cashback: bool,
        token_program: Pubkey = TOKEN_2022_PROGRAM,
    ):
        idl = IDLParser(str(IDL_PATH))
        abc = derive_associated_bonding_curve(_MINT, _BC, token_program)
        return build_sell_instructions(
            idl=idl,
            mint=_MINT,
            user=_USER,
            bonding_curve=_BC,
            assoc_bc=abc,
            creator=_CREATOR,
            is_mayhem=is_mayhem,
            token_amount=1_000_000,
            min_sol_output=0,
            is_cashback=is_cashback,
            token_program=token_program,
        )

    def _get_fee_recipient(self, ixs):
        sell_ix = ixs[0]
        return sell_ix.accounts[1].pubkey

    def test_bc_sell_1_standard_no_cashback(self):
        """BC-SELL-1: Standard sell — 15 accounts (14 fixed + bonding_curve_v2)."""
        ixs = self._build_sell(is_mayhem=False, is_cashback=False)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 15
        assert self._get_fee_recipient(ixs) == PUMP_FEE

    def test_bc_sell_2_mayhem_no_cashback(self):
        """BC-SELL-2: Mayhem sell — 15 accounts, fee → PUMP_MAYHEM_FEE."""
        ixs = self._build_sell(is_mayhem=True, is_cashback=False)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 15
        assert self._get_fee_recipient(ixs) == PUMP_MAYHEM_FEE

    def test_bc_sell_3_cashback(self):
        """BC-SELL-3: Cashback sell — 16 accounts (user_volume_accumulator added)."""
        ixs = self._build_sell(is_mayhem=False, is_cashback=True)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 16
        assert self._get_fee_recipient(ixs) == PUMP_FEE

    def test_bc_sell_4_mayhem_plus_cashback(self):
        """BC-SELL-4: Mayhem + cashback — 16 accounts, fee → PUMP_MAYHEM_FEE."""
        ixs = self._build_sell(is_mayhem=True, is_cashback=True)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 16
        assert self._get_fee_recipient(ixs) == PUMP_MAYHEM_FEE

    def test_bc_sell_5_legacy_spl_no_cashback(self):
        """BC-SELL-5: Legacy SPL Token — 15 accounts, token_program = TOKEN_PROGRAM."""
        ixs = self._build_sell(is_mayhem=False, is_cashback=False, token_program=TOKEN_PROGRAM)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 15
        assert sell_ix.accounts[9].pubkey == TOKEN_PROGRAM

    def test_bc_sell_legacy_spl_with_cashback(self):
        """Legacy SPL + cashback — 16 accounts."""
        ixs = self._build_sell(is_mayhem=False, is_cashback=True, token_program=TOKEN_PROGRAM)
        sell_ix = ixs[0]
        assert len(sell_ix.accounts) == 16
        assert sell_ix.accounts[9].pubkey == TOKEN_PROGRAM


# ATA derivation: Token-2022 vs SPL produce different addresses


class TestATADerivation:
    """Verify ATA addresses differ between SPL and Token-2022 for same mint."""

    def test_ata_differs_by_token_program(self):
        """ATA for Token-2022 != ATA for SPL Token, even for the same mint + owner."""
        from spl.token.instructions import get_associated_token_address

        ata_2022 = get_associated_token_address(_USER, _MINT, TOKEN_2022_PROGRAM)
        ata_spl = get_associated_token_address(_USER, _MINT, TOKEN_PROGRAM)
        assert ata_2022 != ata_spl

    def test_associated_bonding_curve_differs_by_token_program(self):
        """Associated bonding curve address differs between Token-2022 and SPL."""
        abc_2022 = derive_associated_bonding_curve(_MINT, _BC, TOKEN_2022_PROGRAM)
        abc_spl = derive_associated_bonding_curve(_MINT, _BC, TOKEN_PROGRAM)
        assert abc_2022 != abc_spl


# Sell instruction data: verify no track_volume leakage into wrong field


class TestSellInstructionData:
    """Verify sell instruction data format is correct for all combinations."""

    def _build_sell_data(self, *, is_cashback: bool):
        idl = IDLParser(str(IDL_PATH))
        abc = derive_associated_bonding_curve(_MINT, _BC, TOKEN_2022_PROGRAM)
        ixs = build_sell_instructions(
            idl=idl,
            mint=_MINT,
            user=_USER,
            bonding_curve=_BC,
            assoc_bc=abc,
            creator=_CREATOR,
            is_mayhem=False,
            token_amount=500_000,
            min_sol_output=100_000,
            is_cashback=is_cashback,
        )
        return ixs[0].data

    def test_sell_data_length(self):
        """Sell data: 8 (disc) + 8 (amount) + 8 (min_sol) = 24 bytes (no track_volume)."""
        data = self._build_sell_data(is_cashback=False)
        assert len(data) == 24

    def test_sell_data_same_regardless_of_cashback(self):
        """Instruction data is identical for cashback vs non-cashback (only accounts differ)."""
        data_no_cb = self._build_sell_data(is_cashback=False)
        data_cb = self._build_sell_data(is_cashback=True)
        assert data_no_cb == data_cb
