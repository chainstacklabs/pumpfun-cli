from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import derive_associated_bonding_curve, derive_bonding_curve
from pumpfun_cli.protocol.contracts import BUY_EXACT_SOL_IN_DISCRIMINATOR
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_sol_in_instructions,
    build_buy_instructions,
    build_sell_instructions,
)

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
