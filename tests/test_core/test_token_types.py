"""Every kind of coin the program issues trades through the same v2 path.

Mayhem, cashback, holder-reward and legacy SPL Token coins differ only in
which fee recipients and token program the accounts derive from.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from pumpfun_cli.core.trade import buy_token, sell_token
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import find_ata
from pumpfun_cli.protocol.contracts import (
    NORMAL_FEE_RECIPIENTS,
    PUMP_PROGRAM,
    RESERVED_FEE_RECIPIENTS,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from tests.test_core.helpers import COIN, build_curve_data, chain_with_coin

CASES = {
    "standard": ({}, TOKEN_2022_PROGRAM, NORMAL_FEE_RECIPIENTS),
    "mayhem": ({"mayhem": True}, TOKEN_2022_PROGRAM, RESERVED_FEE_RECIPIENTS),
    "cashback": ({"cashback": True}, TOKEN_2022_PROGRAM, NORMAL_FEE_RECIPIENTS),
    "holder_reward": ({"holder_reward": True}, TOKEN_2022_PROGRAM, NORMAL_FEE_RECIPIENTS),
    "legacy_spl": ({"length": 151}, TOKEN_PROGRAM, NORMAL_FEE_RECIPIENTS),
}


def _chain(curve_kwargs, program):
    client = chain_with_coin(curve=build_curve_data(**curve_kwargs))
    client.add_mint(COIN, 6, program)
    return client


@pytest.mark.parametrize("case", CASES)
async def test_buy_and_sell(tmp_keystore, case):
    curve_kwargs, program, recipients = CASES[case]
    user = decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()
    client = _chain(curve_kwargs, program)
    client.token_balances[find_ata(user, COIN, program)] = 1_000_000
    with patch("pumpfun_cli.core.trade.RpcClient", return_value=client):
        bought = await buy_token("http://rpc", tmp_keystore, "testpass", str(COIN), 0.01)
        sold = await sell_token("http://rpc", tmp_keystore, "testpass", str(COIN), "all")
    assert bought["action"] == "buy" and sold["action"] == "sell"
    for sent in client.sent:
        ix = next(i for i in sent["instructions"] if i.program_id == PUMP_PROGRAM)
        keys = [m.pubkey for m in ix.accounts]
        assert keys[3] == program
        assert keys[6] in recipients
        assert keys[14] == find_ata(user, COIN, program)
