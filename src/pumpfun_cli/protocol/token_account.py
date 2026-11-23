"""The wallet's token account for a coin: what it holds, and closing it once emptied."""

import struct
from dataclasses import dataclass

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from spl.token.instructions import close_account
from spl.token.models import CloseAccountParams

from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM

# SPL token account layout, shared by Token-2022: mint, owner, amount, then
# delegate, state and the optional close authority. Token-2022 follows the
# 165-byte base with one account-type byte and type-length-value extensions;
# TransferFeeAmount holds the fee withheld here.
_OWNER_OFFSET = 32
_AMOUNT_OFFSET = 64
_STATE_OFFSET = 108
_STATE_FROZEN = 2
_CLOSE_AUTHORITY_OFFSET = 129
_EXTENSIONS_OFFSET = 166
_TRANSFER_FEE_AMOUNT = 2
# TransferFeeExtension, then HarvestWithheldTokensToMint.
_HARVEST_WITHHELD_TO_MINT = bytes([26, 4])


@dataclass(frozen=True)
class TokenHolding:
    """A token account's balance, the transfer fee withheld in it, its lamports,
    who may close it (its close authority if set, else its owner) and whether
    it is frozen. Empty when the account does not exist.
    """

    amount: int = 0
    withheld: int = 0
    lamports: int = 0
    closer: Pubkey | None = None
    frozen: bool = False

    def closable_by(self, wallet: Pubkey) -> bool:
        return self.closer == wallet and not self.frozen


def parse_token_account(data: bytes, lamports: int) -> TokenHolding:
    """Decode an SPL Token or Token-2022 token account."""
    amount = struct.unpack_from("<Q", data, _AMOUNT_OFFSET)[0]
    closer = Pubkey.from_bytes(data[_OWNER_OFFSET : _OWNER_OFFSET + 32])
    if struct.unpack_from("<I", data, _CLOSE_AUTHORITY_OFFSET)[0]:
        start = _CLOSE_AUTHORITY_OFFSET + 4
        closer = Pubkey.from_bytes(data[start : start + 32])
    withheld = 0
    offset = _EXTENSIONS_OFFSET
    while offset + 4 <= len(data):
        kind, length = struct.unpack_from("<HH", data, offset)
        if kind == 0 and length == 0:
            break
        if kind == _TRANSFER_FEE_AMOUNT:
            withheld = struct.unpack_from("<Q", data, offset + 4)[0]
            break
        offset += 4 + length
    return TokenHolding(
        amount=amount,
        withheld=withheld,
        lamports=lamports,
        closer=closer,
        frozen=data[_STATE_OFFSET] == _STATE_FROZEN,
    )


def build_harvest_withheld_to_mint_instruction(mint: Pubkey, account: Pubkey) -> Instruction:
    """Move the transfer fee withheld in `account` into its mint. Needs no signer."""
    return Instruction(
        TOKEN_2022_PROGRAM,
        _HARVEST_WITHHELD_TO_MINT,
        [
            AccountMeta(mint, is_signer=False, is_writable=True),
            AccountMeta(account, is_signer=False, is_writable=True),
        ],
    )


def build_close_emptied_account_instructions(
    *, user: Pubkey, mint: Pubkey, account: Pubkey, token_program: Pubkey, withheld: int
) -> list[Instruction]:
    """Close `user`'s token account after a sale empties it; the rent returns to `user`.

    Token-2022 refuses to close an account that still holds withheld transfer
    fees, so those move to the mint first.
    """
    ixs = []
    if withheld and token_program == TOKEN_2022_PROGRAM:
        ixs.append(build_harvest_withheld_to_mint_instruction(mint, account))
    ixs.append(
        close_account(
            CloseAccountParams(program_id=token_program, account=account, dest=user, owner=user)
        )
    )
    return ixs
