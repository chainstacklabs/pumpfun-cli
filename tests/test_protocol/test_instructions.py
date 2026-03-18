from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import derive_associated_bonding_curve, derive_bonding_curve
from pumpfun_cli.protocol.contracts import (
    BUY_EXACT_SOL_IN_DISCRIMINATOR,
    MAYHEM_GLOBAL_PARAMS,
    MAYHEM_PROGRAM_ID,
    MAYHEM_SOL_VAULT,
)
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_sol_in_instructions,
    build_buy_instructions,
    build_create_instructions,
    build_sell_instructions,
)

# create_v2 must always have exactly 16 accounts (including mayhem accounts).
_EXPECTED_CREATE_V2_ACCOUNTS = 16

IDL_PATH = Path(__file__).parent.parent.parent / "idl" / "pump_fun_idl.json"
_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
_USER = Pubkey.from_string("11111111111111111111111111111112")
_BC = derive_bonding_curve(_MINT)
_ABC = derive_associated_bonding_curve(_MINT, _BC)


def test_buy_instructions_returns_two():
    idl = IDLParser(str(IDL_PATH))
    ixs = build_buy_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        bonding_curve=_BC,
        assoc_bc=_ABC,
        creator=_USER,
        is_mayhem=False,
        token_amount=1000,
        max_sol_cost=100_000_000,
    )
    assert len(ixs) == 2


def test_sell_instructions_returns_one():
    idl = IDLParser(str(IDL_PATH))
    ixs = build_sell_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        bonding_curve=_BC,
        assoc_bc=_ABC,
        creator=_USER,
        is_mayhem=False,
        token_amount=1000,
        min_sol_output=0,
    )
    assert len(ixs) == 1


def test_buy_exact_sol_in_returns_two():
    idl = IDLParser(str(IDL_PATH))
    ixs = build_buy_exact_sol_in_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        bonding_curve=_BC,
        assoc_bc=_ABC,
        creator=_USER,
        is_mayhem=False,
        spendable_sol_in=100_000_000,
        min_tokens_out=1000,
    )
    assert len(ixs) == 2


def test_buy_exact_sol_in_discriminator():
    idl = IDLParser(str(IDL_PATH))
    ixs = build_buy_exact_sol_in_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        bonding_curve=_BC,
        assoc_bc=_ABC,
        creator=_USER,
        is_mayhem=False,
        spendable_sol_in=100_000_000,
        min_tokens_out=1000,
    )
    buy_ix = ixs[-1]
    assert buy_ix.data[:8] == BUY_EXACT_SOL_IN_DISCRIMINATOR


def test_create_instructions_cashback_false():
    """create_v2 with is_cashback=False encodes OptionBool as 0x00."""
    idl = IDLParser(str(IDL_PATH))
    ixs = build_create_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        name="Test",
        symbol="TST",
        uri="https://example.com",
        is_mayhem=False,
        is_cashback=False,
    )
    assert len(ixs) == 1
    create_ix = ixs[0]
    # Lock account layout to prevent AccountNotEnoughKeys regressions
    assert len(create_ix.accounts) == _EXPECTED_CREATE_V2_ACCOUNTS
    assert create_ix.accounts[9].pubkey == MAYHEM_PROGRAM_ID
    assert create_ix.accounts[10].pubkey == MAYHEM_GLOBAL_PARAMS
    assert create_ix.accounts[11].pubkey == MAYHEM_SOL_VAULT
    # Last byte should be 0x00 (is_cashback_enabled = false)
    assert create_ix.data[-1:] == b"\x00"
    # Second-to-last byte is is_mayhem_mode = false
    assert create_ix.data[-2:-1] == b"\x00"


def test_create_instructions_cashback_true():
    """create_v2 with is_cashback=True encodes OptionBool as 0x01."""
    idl = IDLParser(str(IDL_PATH))
    ixs = build_create_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        name="Test",
        symbol="TST",
        uri="https://example.com",
        is_mayhem=False,
        is_cashback=True,
    )
    assert len(ixs) == 1
    create_ix = ixs[0]
    assert len(create_ix.accounts) == _EXPECTED_CREATE_V2_ACCOUNTS
    assert create_ix.accounts[9].pubkey == MAYHEM_PROGRAM_ID
    assert create_ix.accounts[10].pubkey == MAYHEM_GLOBAL_PARAMS
    assert create_ix.accounts[11].pubkey == MAYHEM_SOL_VAULT
    # Last byte should be 0x01 (is_cashback_enabled = true)
    assert create_ix.data[-1:] == b"\x01"
    # Second-to-last byte is is_mayhem_mode = false
    assert create_ix.data[-2:-1] == b"\x00"


def test_create_instructions_mayhem_and_cashback():
    """create_v2 with both is_mayhem=True and is_cashback=True."""
    idl = IDLParser(str(IDL_PATH))
    ixs = build_create_instructions(
        idl=idl,
        mint=_MINT,
        user=_USER,
        name="Test",
        symbol="TST",
        uri="https://example.com",
        is_mayhem=True,
        is_cashback=True,
    )
    assert len(ixs) == 1
    create_ix = ixs[0]
    assert len(create_ix.accounts) == _EXPECTED_CREATE_V2_ACCOUNTS
    assert create_ix.accounts[9].pubkey == MAYHEM_PROGRAM_ID
    assert create_ix.accounts[10].pubkey == MAYHEM_GLOBAL_PARAMS
    assert create_ix.accounts[11].pubkey == MAYHEM_SOL_VAULT
    # Last byte = cashback true, second-to-last = mayhem true
    assert create_ix.data[-1:] == b"\x01"
    assert create_ix.data[-2:-1] == b"\x01"
