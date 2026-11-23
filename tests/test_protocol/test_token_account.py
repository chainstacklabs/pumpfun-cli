"""Reading a wallet token account, and closing it once a sale empties it."""

import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from pumpfun_cli.protocol.token_account import (
    TokenHolding,
    build_close_emptied_account_instructions,
    parse_token_account,
)

MINT = Pubkey.new_unique()
OWNER = Pubkey.new_unique()
ACCOUNT = Pubkey.new_unique()


def _account(
    amount: int,
    extensions: list[tuple[int, bytes]] | None = None,
    *,
    close_authority: Pubkey | None = None,
    state: int = 1,
) -> bytes:
    """A token account; with `extensions`, a Token-2022 one carrying them."""
    data = bytearray(165)
    data[:32] = bytes(MINT)
    data[32:64] = bytes(OWNER)
    struct.pack_into("<Q", data, 64, amount)
    data[108] = state
    if close_authority is not None:
        struct.pack_into("<I", data, 129, 1)
        data[133:165] = bytes(close_authority)
    if extensions is not None:
        data += bytes([2])  # account type: Account
        for kind, value in extensions:
            data += struct.pack("<HH", kind, len(value)) + value
    return bytes(data)


def test_an_spl_account_has_no_withheld_fee():
    assert parse_token_account(_account(42), 2_039_280) == TokenHolding(
        42, 0, 2_039_280, closer=OWNER
    )


def test_the_owner_closes_an_account_without_a_close_authority():
    assert parse_token_account(_account(0), 1).closable_by(OWNER)


def test_a_close_authority_takes_the_close_from_the_owner():
    other = Pubkey.new_unique()
    holding = parse_token_account(_account(0, [(7, b"")], close_authority=other), 1)
    assert holding.closer == other
    assert not holding.closable_by(OWNER)


def test_a_frozen_account_cannot_be_closed():
    holding = parse_token_account(_account(0, state=2), 1)
    assert holding.frozen and not holding.closable_by(OWNER)


def test_withheld_fee_is_read_past_other_extensions():
    # ImmutableOwner (7, empty) first, as the ATA program writes it, then TransferFeeAmount.
    data = _account(5, [(7, b""), (2, struct.pack("<Q", 1_234))])
    assert parse_token_account(data, 1).withheld == 1_234


def test_a_token_2022_account_without_a_transfer_fee():
    assert parse_token_account(_account(5, [(7, b"")]), 1).withheld == 0


def test_close_needs_no_harvest_when_nothing_is_withheld():
    for program in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
        (close,) = build_close_emptied_account_instructions(
            user=OWNER, mint=MINT, account=ACCOUNT, token_program=program, withheld=0
        )
        assert close.program_id == program and bytes(close.data) == bytes([9])
        assert [m.pubkey for m in close.accounts] == [ACCOUNT, OWNER, OWNER]


def test_withheld_fees_go_to_the_mint_before_the_close():
    harvest, close = build_close_emptied_account_instructions(
        user=OWNER, mint=MINT, account=ACCOUNT, token_program=TOKEN_2022_PROGRAM, withheld=9
    )
    assert harvest.program_id == TOKEN_2022_PROGRAM
    assert bytes(harvest.data) == bytes([26, 4])
    assert [(m.pubkey, m.is_writable, m.is_signer) for m in harvest.accounts] == [
        (MINT, True, False),
        (ACCOUNT, True, False),
    ]
    assert bytes(close.data) == bytes([9])


async def test_client_reads_the_account_at_confirmed():
    client = RpcClient("http://rpc")
    value = SimpleNamespace(data=_account(7, [(2, struct.pack("<Q", 3))]), lamports=2_074_080)
    client.rpc.get_account_info = AsyncMock(return_value=SimpleNamespace(value=value))
    holding = await client.get_token_account(ACCOUNT)
    assert holding == TokenHolding(7, 3, 2_074_080, closer=OWNER)
    assert client.rpc.get_account_info.call_args.kwargs["commitment"] == "confirmed"


async def test_client_reads_a_missing_account_as_empty():
    client = RpcClient("http://rpc")
    client.rpc.get_account_info = AsyncMock(return_value=SimpleNamespace(value=None))
    assert await client.get_token_account(ACCOUNT) == TokenHolding()
