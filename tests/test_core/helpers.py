"""Shared test helpers for core tests."""

import struct

from solders.pubkey import Pubkey


def build_pool_data(
    *,
    index: int = 1,
    creator: Pubkey | None = None,
    mint: Pubkey | None = None,
) -> bytes:
    """Build minimal synthetic PumpSwap pool data for mocking.

    Returns a 243-byte blob matching the on-chain pool account layout.
    """
    _creator = bytes(creator or Pubkey.from_string("11111111111111111111111111111112"))
    _mint = bytes(mint or Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"))
    wsol = bytes(Pubkey.from_string("So11111111111111111111111111111111111111112"))
    filler = bytes(Pubkey.from_string("11111111111111111111111111111113"))

    data = bytearray(243)
    data[0:8] = b"\x00" * 8  # discriminator
    data[8] = 255  # pool_bump
    struct.pack_into("<H", data, 9, index)
    data[11:43] = _creator
    data[43:75] = _mint
    data[75:107] = wsol
    data[107:139] = filler  # lp_mint
    data[139:171] = filler  # pool_base_token_account
    data[171:203] = filler  # pool_quote_token_account
    struct.pack_into("<Q", data, 203, 1_000_000)  # lp_supply
    data[211:243] = _creator  # coin_creator
    return bytes(data)
