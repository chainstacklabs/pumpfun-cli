"""Core trade tests for all token type combinations.

Tests buy_token and sell_token with different bonding curve state flags:
mayhem, cashback, SPL vs Token-2022. Verifies correct instruction
building and fee routing through mocked RPC.

Ref: docs/token-types-test-matrix.md
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.trade import buy_token, sell_token
from pumpfun_cli.protocol.contracts import (
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)

_MINT_STR = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_CREATOR_BYTES = bytes(Pubkey.from_string("11111111111111111111111111111112"))


def _bc_state(
    *,
    is_mayhem: bool = False,
    is_cashback: bool = False,
    complete: bool = False,
):
    """Build a bonding curve state dict with given flags."""
    return {
        "complete": complete,
        "virtual_token_reserves": 1_000_000_000_000,
        "virtual_sol_reserves": 30_000_000_000,
        "real_sol_reserves": 10_000_000_000,
        "creator": _CREATOR_BYTES,
        "is_mayhem_mode": is_mayhem,
        "is_cashback_coin": is_cashback,
    }


def _patch_token_program(program: Pubkey):
    return patch(
        "pumpfun_cli.core.trade.get_token_program_id",
        new=AsyncMock(return_value=program),
    )


def _setup_buy_mocks(MockClient, MockIDL, state):
    client = AsyncMock()
    MockClient.return_value = client
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = b"\x00" * 200
    client.get_account_info.return_value = resp
    client.get_balance.return_value = 10_000_000_000
    client.send_tx.return_value = "sig"
    client.close = AsyncMock()

    idl = MagicMock()
    MockIDL.return_value = idl
    idl.decode_account_data.return_value = state
    idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

    return client, idl


def _setup_sell_mocks(MockClient, MockIDL, state):
    client = AsyncMock()
    MockClient.return_value = client
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = b"\x00" * 200
    client.get_account_info.return_value = resp
    client.get_token_account_balance.return_value = 1_000_000
    client.send_tx.return_value = "sig"
    client.close = AsyncMock()

    idl = MagicMock()
    MockIDL.return_value = idl
    idl.decode_account_data.return_value = state
    idl.get_instruction_discriminators.return_value = {"sell": b"\x00" * 8}

    return client, idl


# ---------------------------------------------------------------------------
# Buy: Token-2022 standard (no mayhem, no cashback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_standard_token2022(tmp_keystore):
    """BC-BUY-1: Standard Token-2022 buy succeeds."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_buy_mocks(MockClient, MockIDL, _bc_state())

        result = await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert result["action"] == "buy"
    assert result["signature"] == "sig"


# ---------------------------------------------------------------------------
# Buy: Mayhem token (fee → PUMP_MAYHEM_FEE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_mayhem_token(tmp_keystore):
    """BC-BUY-2: Mayhem token buy — passes is_mayhem=True to instruction builder."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_buy_exact_sol_in_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_buy_mocks(MockClient, MockIDL, _bc_state(is_mayhem=True))
        mock_build.return_value = []

        await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    call_kwargs = mock_build.call_args
    assert call_kwargs.kwargs.get("is_mayhem") is True


# ---------------------------------------------------------------------------
# Buy: Cashback token (buy always includes volume accumulator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_cashback_token(tmp_keystore):
    """BC-BUY-3: Cashback token buy succeeds (buy instructions are same regardless)."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_buy_mocks(MockClient, MockIDL, _bc_state(is_cashback=True))

        result = await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert result["action"] == "buy"


# ---------------------------------------------------------------------------
# Buy: Mayhem + cashback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_mayhem_cashback_token(tmp_keystore):
    """BC-BUY-4: Mayhem + cashback buy — is_mayhem passed through."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_buy_exact_sol_in_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_buy_mocks(MockClient, MockIDL, _bc_state(is_mayhem=True, is_cashback=True))
        mock_build.return_value = []

        await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert mock_build.call_args.kwargs.get("is_mayhem") is True


# ---------------------------------------------------------------------------
# Buy: Legacy SPL token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_legacy_spl_token(tmp_keystore):
    """BC-BUY-5: Legacy SPL Token buy — token_program=TOKEN_PROGRAM passed through."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_buy_exact_sol_in_instructions") as mock_build,
        _patch_token_program(TOKEN_PROGRAM),
    ):
        _setup_buy_mocks(MockClient, MockIDL, _bc_state())
        mock_build.return_value = []

        await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert mock_build.call_args.kwargs.get("token_program") == TOKEN_PROGRAM


# ---------------------------------------------------------------------------
# Sell: Standard no-cashback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_standard_no_cashback(tmp_keystore):
    """BC-SELL-1: Standard sell — is_cashback=False passed to builder."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_sell_mocks(MockClient, MockIDL, _bc_state(is_cashback=False))
        mock_build.return_value = []

        await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "1.0")

    assert mock_build.call_args.kwargs.get("is_cashback") is False


# ---------------------------------------------------------------------------
# Sell: Mayhem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_mayhem_token(tmp_keystore):
    """BC-SELL-2: Mayhem sell — is_mayhem=True passed to builder."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_sell_mocks(MockClient, MockIDL, _bc_state(is_mayhem=True))
        mock_build.return_value = []

        await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "1.0")

    assert mock_build.call_args.kwargs.get("is_mayhem") is True


# ---------------------------------------------------------------------------
# Sell: Cashback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_cashback_token(tmp_keystore):
    """BC-SELL-3: Cashback sell — is_cashback=True passed to builder."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_sell_mocks(MockClient, MockIDL, _bc_state(is_cashback=True))
        mock_build.return_value = []

        await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "1.0")

    assert mock_build.call_args.kwargs.get("is_cashback") is True


# ---------------------------------------------------------------------------
# Sell: Mayhem + cashback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_mayhem_cashback_token(tmp_keystore):
    """BC-SELL-4: Mayhem + cashback sell."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        _setup_sell_mocks(MockClient, MockIDL, _bc_state(is_mayhem=True, is_cashback=True))
        mock_build.return_value = []

        await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "1.0")

    kwargs = mock_build.call_args.kwargs
    assert kwargs.get("is_mayhem") is True
    assert kwargs.get("is_cashback") is True


# ---------------------------------------------------------------------------
# Sell: Legacy SPL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_legacy_spl_token(tmp_keystore):
    """BC-SELL-5: Legacy SPL Token sell — token_program=TOKEN_PROGRAM passed through."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build,
        _patch_token_program(TOKEN_PROGRAM),
    ):
        _setup_sell_mocks(MockClient, MockIDL, _bc_state())
        mock_build.return_value = []

        await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "1.0")

    assert mock_build.call_args.kwargs.get("token_program") == TOKEN_PROGRAM


# ---------------------------------------------------------------------------
# Buy: Graduated token error message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_graduated_token_error(tmp_keystore):
    """BC-BUY-8: Buying a graduated token returns error with force-amm hint."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = _bc_state(complete=True)

        result = await buy_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert result["error"] == "graduated"


# ---------------------------------------------------------------------------
# Sell: Graduated token error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_graduated_token_error(tmp_keystore):
    """BC-SELL-10: Selling a graduated token returns error."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _patch_token_program(TOKEN_2022_PROGRAM),
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = _bc_state(complete=True)

        result = await sell_token("http://rpc", tmp_keystore, "testpass", _MINT_STR, "all")

    assert result["error"] == "graduated"


# ---------------------------------------------------------------------------
# PumpSwap: Token-2022 and SPL token program pass-through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pumpswap_buy_passes_token_program(tmp_keystore):
    """PS-BUY-1/PS-BUY-2: PumpSwap buy forwards detected token_program."""
    from pumpfun_cli.core.pumpswap import buy_pumpswap
    from pumpfun_cli.protocol.contracts import (
        GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET,
        STANDARD_PUMPSWAP_FEE_RECIPIENT,
    )
    from tests.test_core.helpers import build_pool_data

    pool_data = build_pool_data()

    pool_resp = MagicMock()
    pool_resp.value = MagicMock()
    pool_resp.value.data = pool_data

    off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET
    config_data = bytearray(off + 32)
    config_data[off : off + 32] = bytes(STANDARD_PUMPSWAP_FEE_RECIPIENT)
    gc_resp = MagicMock()
    gc_resp.value = MagicMock()
    gc_resp.value.data = bytes(config_data)

    tp_resp = MagicMock()
    tp_resp.value = MagicMock()
    tp_resp.value.owner = TOKEN_2022_PROGRAM

    vol_resp = MagicMock()
    vol_resp.value = None

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [pool_resp, tp_resp, gc_resp, vol_resp]
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "ps_sig"
        client.close = AsyncMock()

        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", _MINT_STR, 0.01)

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
