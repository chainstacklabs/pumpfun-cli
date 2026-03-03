"""Tests for protocol/pumpswap.py async functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import (
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET,
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from pumpfun_cli.protocol.pumpswap import (
    get_fee_recipients,
    get_pool_price,
    get_token_program_id,
)

# --- get_fee_recipients tests ---


@pytest.mark.asyncio
async def test_get_fee_recipients_from_global_config():
    """Fee recipient is read from GlobalConfig at protocol_fee_recipient offset."""
    pool_data = b"\x00" * 243
    client = AsyncMock()
    config_resp = MagicMock()
    config_resp.value = MagicMock()
    off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET
    config_data = bytearray(off + 32)
    expected_recipient = Pubkey.from_string("11111111111111111111111111111115")
    config_data[off : off + 32] = bytes(expected_recipient)
    config_resp.value.data = bytes(config_data)
    client.get_account_info.return_value = config_resp

    fee_recipient, fee_ata = await get_fee_recipients(client, pool_data)
    assert fee_recipient == expected_recipient


@pytest.mark.asyncio
async def test_get_fee_recipients_fallback():
    """Falls back to standard fee recipient when GlobalConfig unavailable."""
    pool_data = b"\x00" * 243
    client = AsyncMock()
    config_resp = MagicMock()
    config_resp.value = None
    client.get_account_info.return_value = config_resp

    fee_recipient, fee_ata = await get_fee_recipients(client, pool_data)
    assert fee_recipient == STANDARD_PUMPSWAP_FEE_RECIPIENT


# --- get_token_program_id tests ---


@pytest.mark.asyncio
async def test_get_token_program_id_standard():
    client = AsyncMock()
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.owner = TOKEN_PROGRAM
    client.get_account_info.return_value = resp

    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    result = await get_token_program_id(client, mint)
    assert result == TOKEN_PROGRAM


@pytest.mark.asyncio
async def test_get_token_program_id_token2022():
    client = AsyncMock()
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.owner = TOKEN_2022_PROGRAM
    client.get_account_info.return_value = resp

    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    result = await get_token_program_id(client, mint)
    assert result == TOKEN_2022_PROGRAM


@pytest.mark.asyncio
async def test_get_token_program_id_unknown():
    client = AsyncMock()
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.owner = Pubkey.from_string("11111111111111111111111111111111")
    client.get_account_info.return_value = resp

    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    with pytest.raises(RuntimeError, match="Unknown token program"):
        await get_token_program_id(client, mint)


@pytest.mark.asyncio
async def test_get_token_program_id_not_found():
    client = AsyncMock()
    resp = MagicMock()
    resp.value = None
    client.get_account_info.return_value = resp

    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    with pytest.raises(RuntimeError, match="Mint account not found"):
        await get_token_program_id(client, mint)


# --- get_pool_price tests ---


@pytest.mark.asyncio
async def test_get_pool_price_normal():
    client = AsyncMock()
    # base=1M tokens, quote=30B lamports => price = 30000
    client.get_token_account_balance.side_effect = [1_000_000, 30_000_000_000]

    pool = {
        "pool_base_token_account": Pubkey.from_string("11111111111111111111111111111113"),
        "pool_quote_token_account": Pubkey.from_string("11111111111111111111111111111114"),
    }
    price = await get_pool_price(client, pool)
    assert price == 30_000.0


@pytest.mark.asyncio
async def test_get_pool_price_zero_base():
    client = AsyncMock()
    client.get_token_account_balance.side_effect = [0, 30_000_000_000]

    pool = {
        "pool_base_token_account": Pubkey.from_string("11111111111111111111111111111113"),
        "pool_quote_token_account": Pubkey.from_string("11111111111111111111111111111114"),
    }
    price = await get_pool_price(client, pool)
    assert price == 0.0
