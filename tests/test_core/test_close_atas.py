"""Closing the wallet's empty token accounts (`wallet close-atas`)."""

from unittest.mock import AsyncMock, MagicMock, patch

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from pumpfun_cli.core.wallet import close_empty_atas
from pumpfun_cli.crypto import encrypt_keypair
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from pumpfun_cli.protocol.token_account import TokenHolding
from tests.test_core.helpers import assert_closes, assert_harvests, closed_accounts


def _wallet(tmp_path) -> tuple[str, Pubkey]:
    keypair = Keypair()
    encrypt_keypair(keypair, "testpass", tmp_path / "wallet.enc")
    return str(tmp_path / "wallet.enc"), keypair.pubkey()


def _client(accounts: list[tuple[Pubkey, TokenHolding]]) -> MagicMock:
    """A client holding `accounts` as (token program, holding), each at a fresh address."""
    rows = [(Pubkey.new_unique(), Pubkey.new_unique(), program, h) for program, h in accounts]
    client = MagicMock()
    client.rows = rows

    async def holdings(owner, program):
        return [(a, m, h) for a, m, p, h in rows if p == program]

    async def parsed(owner, program, commitment=None):
        return [
            {"address": str(a), "mint": str(m), "amount": h.amount, "program": str(p)}
            for a, m, p, h in rows
            if p == program
        ]

    client.get_token_holdings = holdings
    client.get_token_accounts_by_owner = parsed
    client.send_tx = AsyncMock(return_value="sig")
    client.close = AsyncMock()
    return client


async def _run(tmp_path, accounts, **kwargs):
    keyfile, user = _wallet(tmp_path)
    holdings = [(p, TokenHolding(**{"closer": user, **h})) for p, h in accounts]
    client = _client(holdings)
    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=client):
        result = await close_empty_atas("http://rpc", keyfile, "testpass", **kwargs)
    return result, client, user


async def test_withheld_fees_are_harvested_and_rent_is_what_the_accounts_held(tmp_path):
    result, client, user = await _run(
        tmp_path,
        [
            (TOKEN_PROGRAM, {"lamports": 2_039_280}),
            (TOKEN_2022_PROGRAM, {"lamports": 1_513_840, "withheld": 42}),
            (TOKEN_2022_PROGRAM, {"amount": 5, "lamports": 1_513_840}),
        ],
    )
    (spl, _, spl_prog, _), (t22, t22_mint, _, _), _ = client.rows
    close_spl, harvest, close_t22 = client.send_tx.call_args.args[0]
    assert_closes(close_spl, spl, user, spl_prog)
    assert_harvests(harvest, t22_mint, t22)
    assert_closes(close_t22, t22, user, TOKEN_2022_PROGRAM)
    assert result["closed"] == 2
    assert result["recovered_sol"] == (2_039_280 + 1_513_840) / 10**9
    assert result["recovered_sol_raw"] == 2_039_280 + 1_513_840
    assert "skipped" not in result


async def test_accounts_the_wallet_cant_close_are_left_out_of_the_batch(tmp_path):
    other = Pubkey.new_unique()
    result, client, user = await _run(
        tmp_path,
        [
            (TOKEN_PROGRAM, {"lamports": 2_039_280}),
            (TOKEN_2022_PROGRAM, {"lamports": 1, "frozen": True}),
            (TOKEN_2022_PROGRAM, {"lamports": 1, "closer": other}),
        ],
    )
    ok, frozen, foreign = (row[0] for row in client.rows)
    assert closed_accounts(client.send_tx.call_args.args[0]) == [ok]
    assert result["closed"] == 1
    assert result["skipped"] == [
        {"address": str(frozen), "mint": str(client.rows[1][1]), "reason": "frozen"},
        {"address": str(foreign), "mint": str(client.rows[2][1]), "reason": "close_authority"},
    ]


async def test_nothing_closable_sends_nothing(tmp_path):
    result, client, _ = await _run(tmp_path, [(TOKEN_2022_PROGRAM, {"frozen": True})])
    client.send_tx.assert_not_called()
    assert result["closed"] == 0 and result["signature"] is None
    assert result["skipped"][0]["reason"] == "frozen"


async def test_a_run_closes_twenty_with_compute_for_each(tmp_path):
    result, client, _ = await _run(tmp_path, [(TOKEN_PROGRAM, {"lamports": 1})] * 25)
    assert result["closed"] == 20
    assert len(client.send_tx.call_args.args[0]) == 20
    assert client.send_tx.call_args.kwargs["compute_units"] == 100_000


async def test_compute_units_override(tmp_path):
    _, client, _ = await _run(tmp_path, [(TOKEN_PROGRAM, {})], compute_units=55_000)
    assert client.send_tx.call_args.kwargs["compute_units"] == 55_000
