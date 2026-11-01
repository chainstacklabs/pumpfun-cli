"""Base mints owned by either token program derive their accounts under that program."""

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import derive_bonding_curve, find_ata
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_quote_in_v2_instruction,
    build_sell_v2_instruction,
)

USER = Pubkey.new_unique()
MINT = Pubkey.new_unique()
CREATOR = Pubkey.new_unique()


@pytest.mark.parametrize("program", [TOKEN_PROGRAM, TOKEN_2022_PROGRAM])
def test_base_accounts_follow_the_mints_program(program):
    for built in (
        build_buy_exact_quote_in_v2_instruction(
            mint=MINT,
            creator=CREATOR,
            user=USER,
            spendable_quote_in=1,
            min_tokens_out=1,
            base_token_program=program,
        ),
        build_sell_v2_instruction(
            mint=MINT,
            creator=CREATOR,
            user=USER,
            token_amount=1,
            min_quote_out=1,
            base_token_program=program,
        ),
    ):
        keys = [m.pubkey for m in built.accounts]
        assert keys[3] == program
        assert keys[11] == find_ata(derive_bonding_curve(MINT), MINT, program)
        assert keys[14] == find_ata(USER, MINT, program)
