"""Tests for claim-cashback, close-volume-acc, and migrate instruction builders."""

from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import (
    COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
    COLLECT_CREATOR_FEE_DISCRIMINATOR,
    PUMP_AMM_PROGRAM,
    PUMP_PROGRAM,
)
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_claim_cashback_instruction,
    build_close_volume_accumulator_instruction,
    build_collect_coin_creator_fee_instruction,
    build_collect_creator_fee_instruction,
    build_migrate_instruction,
)

IDL_PATH = Path(__file__).parent.parent.parent / "idl" / "pump_fun_idl.json"
_USER = Pubkey.from_string("11111111111111111111111111111112")
_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
_WA = Pubkey.from_string("11111111111111111111111111111113")


def test_claim_cashback_has_5_accounts():
    idl = IDLParser(str(IDL_PATH))
    ix = build_claim_cashback_instruction(idl=idl, user=_USER)
    assert len(ix.accounts) == 5
    assert ix.program_id == PUMP_PROGRAM
    assert ix.accounts[0].pubkey == _USER
    assert ix.accounts[0].is_signer is False
    assert ix.accounts[0].is_writable is True


def test_close_volume_accumulator_has_4_accounts():
    idl = IDLParser(str(IDL_PATH))
    ix = build_close_volume_accumulator_instruction(idl=idl, user=_USER)
    assert len(ix.accounts) == 4
    assert ix.program_id == PUMP_PROGRAM
    assert ix.accounts[0].pubkey == _USER
    assert ix.accounts[0].is_signer is True


def test_migrate_has_24_accounts():
    idl = IDLParser(str(IDL_PATH))
    ix = build_migrate_instruction(idl=idl, mint=_MINT, user=_USER, withdraw_authority=_WA)
    assert len(ix.accounts) == 24
    assert ix.program_id == PUMP_PROGRAM


def test_migrate_user_is_signer():
    idl = IDLParser(str(IDL_PATH))
    ix = build_migrate_instruction(idl=idl, mint=_MINT, user=_USER, withdraw_authority=_WA)
    user_account = ix.accounts[5]
    assert user_account.pubkey == _USER
    assert user_account.is_signer is True


def test_migrate_includes_amm_program():
    idl = IDLParser(str(IDL_PATH))
    ix = build_migrate_instruction(idl=idl, mint=_MINT, user=_USER, withdraw_authority=_WA)
    account_pubkeys = [a.pubkey for a in ix.accounts]
    assert PUMP_AMM_PROGRAM in account_pubkeys


def test_collect_creator_fee_has_5_accounts():
    idl = IDLParser(str(IDL_PATH))
    ix = build_collect_creator_fee_instruction(idl=idl, creator=_USER)
    assert len(ix.accounts) == 5
    assert ix.program_id == PUMP_PROGRAM
    assert ix.data[:8] == COLLECT_CREATOR_FEE_DISCRIMINATOR


def test_claim_cashback_user_not_signer():
    """claim_cashback account[0] (user) must be is_signer=False per IDL."""
    idl = IDLParser(str(IDL_PATH))
    ix = build_claim_cashback_instruction(idl=idl, user=_USER)
    assert ix.accounts[0].pubkey == _USER
    assert ix.accounts[0].is_signer is False


def test_collect_coin_creator_fee_has_8_accounts():
    ix = build_collect_coin_creator_fee_instruction(creator=_USER)
    assert len(ix.accounts) == 8
    assert ix.program_id == PUMP_AMM_PROGRAM
    assert ix.data[:8] == COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR


def test_collect_coin_creator_fee_last_account_is_program():
    """collect_coin_creator_fee 8th account must be PUMP_AMM_PROGRAM."""
    ix = build_collect_coin_creator_fee_instruction(creator=_USER)
    assert ix.accounts[7].pubkey == PUMP_AMM_PROGRAM
