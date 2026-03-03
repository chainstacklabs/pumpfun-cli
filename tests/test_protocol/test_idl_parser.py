from pathlib import Path

from pumpfun_cli.protocol.idl_parser import IDLParser

IDL_PATH = Path(__file__).parent.parent.parent / "idl" / "pump_fun_idl.json"


def test_load_idl():
    parser = IDLParser(str(IDL_PATH))
    assert parser is not None


def test_discriminators_contain_buy_sell():
    parser = IDLParser(str(IDL_PATH))
    discs = parser.get_instruction_discriminators()
    assert "buy" in discs
    assert "sell" in discs
    assert "create_v2" in discs
    assert "extend_account" in discs


def test_discriminators_are_8_bytes():
    parser = IDLParser(str(IDL_PATH))
    discs = parser.get_instruction_discriminators()
    for name, disc in discs.items():
        assert len(disc) == 8, f"{name} discriminator is {len(disc)} bytes"
