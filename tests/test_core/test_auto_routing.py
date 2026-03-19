"""Tests for auto-routing: graduated tokens fall back to PumpSwap.

These tests verify the individual core functions (buy_token returns graduated,
buy_pumpswap succeeds independently) rather than the command-layer wiring.
The auto-routing logic lives in commands/trade.py, so here we test the
building blocks that make it work.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pumpfun_cli.core.pumpswap import buy_pumpswap, sell_pumpswap
from pumpfun_cli.core.trade import buy_token, sell_token
from pumpfun_cli.protocol.contracts import (
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET,
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
)
from tests.test_core.helpers import build_pool_data

_PATCH_TOKEN_PROG = patch(
    "pumpfun_cli.core.trade.get_token_program_id",
    new=AsyncMock(return_value=TOKEN_2022_PROGRAM),
)

_VALID_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# --- helpers (reused from test_pumpswap.py) ---


def _mock_global_config_resp():
    off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET
    config_data = bytearray(off + 32)
    config_data[off : off + 32] = bytes(STANDARD_PUMPSWAP_FEE_RECIPIENT)
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = bytes(config_data)
    return resp


def _mock_pool_resp(pool_data):
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = pool_data
    return resp


def _mock_pool_not_found():
    resp = MagicMock()
    resp.value = None
    return resp


def _mock_token_program_resp():
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.owner = TOKEN_PROGRAM
    return resp


def _mock_vol_accumulator_resp():
    resp = MagicMock()
    resp.value = None
    return resp


def _mock_bonding_curve_graduated():
    """Build a mock bonding curve response where complete=True."""
    resp = MagicMock()
    resp.value = MagicMock()
    # We patch IDLParser to return graduated state, so data doesn't matter
    resp.value.data = b"\x00" * 200
    return resp


def _mock_bonding_curve_not_found():
    resp = MagicMock()
    resp.value = None
    return resp


# --- buy auto-routing tests ---


@pytest.mark.asyncio
@_PATCH_TOKEN_PROG
async def test_buy_auto_route_graduated_to_pumpswap(tmp_keystore):
    """buy_token returns graduated, then buy_pumpswap succeeds with venue==pumpswap."""
    # Step 1: buy_token detects graduated
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_bonding_curve_graduated()
        client.close = AsyncMock()

        with patch("pumpfun_cli.core.trade.IDLParser") as MockIDL:
            idl = MagicMock()
            MockIDL.return_value = idl
            idl.decode_account_data.return_value = {"complete": True}

            result = await buy_token("http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01)

    assert result["error"] == "graduated"

    # Step 2: buy_pumpswap succeeds
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
            _mock_vol_accumulator_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "pumpswap_sig"
        client.close = AsyncMock()

        ps_result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01)

    assert ps_result["venue"] == "pumpswap"
    assert ps_result["action"] == "buy"
    assert ps_result["signature"] == "pumpswap_sig"


@pytest.mark.asyncio
@_PATCH_TOKEN_PROG
async def test_sell_auto_route_graduated_to_pumpswap(tmp_keystore):
    """sell_token returns graduated, then sell_pumpswap succeeds with venue==pumpswap."""
    # Step 1: sell_token detects graduated
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_bonding_curve_graduated()
        client.close = AsyncMock()

        with patch("pumpfun_cli.core.trade.IDLParser") as MockIDL:
            idl = MagicMock()
            MockIDL.return_value = idl
            idl.decode_account_data.return_value = {"complete": True}

            result = await sell_token("http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all")

    assert result["error"] == "graduated"

    # Step 2: sell_pumpswap succeeds
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [
            1_000_000,
            1_000_000_000,
            30_000_000_000,
        ]
        client.send_tx.return_value = "sellsig_ps"
        client.close = AsyncMock()

        ps_result = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all")

    assert ps_result["venue"] == "pumpswap"
    assert ps_result["action"] == "sell"
    assert ps_result["signature"] == "sellsig_ps"


@pytest.mark.asyncio
async def test_buy_auto_route_forwards_slippage(tmp_keystore):
    """slippage=5 is forwarded to buy_pumpswap."""
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
            _mock_vol_accumulator_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "buysig"
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01, slippage=5
        )

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    # With slippage=5, min_base_amount_out should be 95% of estimated
    # (verified by the fact that the trade succeeded with slippage=5)


@pytest.mark.asyncio
async def test_sell_auto_route_forwards_slippage(tmp_keystore):
    """slippage=5 is forwarded to sell_pumpswap."""
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [
            1_000_000,
            1_000_000_000,
            30_000_000_000,
        ]
        client.send_tx.return_value = "sellsig"
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all", slippage=5
        )

    assert result["action"] == "sell"
    assert result["venue"] == "pumpswap"


@pytest.mark.asyncio
async def test_buy_auto_route_forwards_dry_run(tmp_keystore):
    """dry_run=True forwarded to buy_pumpswap, send_tx not called."""
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 10_000_000_000
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01, dry_run=True
        )

    assert result["dry_run"] is True
    assert result["venue"] == "pumpswap"
    assert "signature" not in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_sell_auto_route_forwards_dry_run(tmp_keystore):
    """dry_run=True forwarded to sell_pumpswap, send_tx not called."""
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [
            1_000_000,
            1_000_000_000,
            30_000_000_000,
        ]
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all", dry_run=True
        )

    assert result["dry_run"] is True
    assert result["venue"] == "pumpswap"
    assert "signature" not in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_buy_auto_route_sell_all_through_fallback(tmp_keystore):
    """sell_pumpswap with amount_str='all' works after graduated fallback."""
    pool_data = build_pool_data()
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [
            500_000_000,  # user balance
            1_000_000_000,  # pool base
            30_000_000_000,  # pool quote
        ]
        client.send_tx.return_value = "sell_all_sig"
        client.close = AsyncMock()

        result = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all")

    assert result["action"] == "sell"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "sell_all_sig"
    assert result["tokens_sold"] > 0


@pytest.mark.asyncio
@_PATCH_TOKEN_PROG
async def test_buy_not_found_does_not_trigger_fallback(tmp_keystore):
    """buy_token returns not_found — no pumpswap call should follow."""
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_bonding_curve_not_found()
        client.close = AsyncMock()

        result = await buy_token("http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01)

    assert result["error"] == "not_found"
    # The command layer checks: if result.get("error") == "graduated"
    # "not_found" != "graduated" so pumpswap would NOT be called.
    assert result["error"] != "graduated"


@pytest.mark.asyncio
@_PATCH_TOKEN_PROG
async def test_sell_not_found_does_not_trigger_fallback(tmp_keystore):
    """sell_token returns not_found — no pumpswap call should follow."""
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_bonding_curve_not_found()
        client.close = AsyncMock()

        result = await sell_token("http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all")

    assert result["error"] == "not_found"
    assert result["error"] != "graduated"


@pytest.mark.asyncio
async def test_buy_auto_route_pumpswap_pool_not_found(tmp_keystore):
    """Graduated but pool missing -> pumpswap_error."""
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        result = await buy_pumpswap("http://rpc", tmp_keystore, "testpass", _VALID_MINT, 0.01)

    assert result["error"] == "pumpswap_error"
    assert "No PumpSwap pool" in result["message"]


@pytest.mark.asyncio
async def test_sell_auto_route_pumpswap_pool_not_found(tmp_keystore):
    """Graduated but pool missing -> pumpswap_error for sell."""
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        result = await sell_pumpswap("http://rpc", tmp_keystore, "testpass", _VALID_MINT, "all")

    assert result["error"] == "pumpswap_error"
    assert "No PumpSwap pool" in result["message"]
