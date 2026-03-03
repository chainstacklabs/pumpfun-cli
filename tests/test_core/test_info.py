"""Unit tests for pumpfun_cli.core.info module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from solders.pubkey import Pubkey

MINT_STR = "72xpy6cejkorDh8gx328CAW3Fq7uCQdCyXkSLAE5to5p"


def _make_state(*, complete: bool = False) -> dict:
    """Return a realistic bonding curve state dict."""
    return {
        "complete": complete,
        "virtual_token_reserves": 1_000_000_000_000,
        "virtual_sol_reserves": 30_000_000_000,
        "real_sol_reserves": 10_000_000_000,
        "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
        "is_mayhem_mode": False,
        "is_cashback_coin": False,
    }


@pytest.fixture()
def _mock_rpc_not_found():
    """Mock RpcClient so get_account_info returns no value."""
    with patch("pumpfun_cli.core.info.RpcClient") as MockRpc:
        instance = AsyncMock()
        resp = MagicMock()
        resp.value = None
        instance.get_account_info.return_value = resp
        MockRpc.return_value = instance
        yield instance


@pytest.fixture()
def _mock_rpc_active():
    """Mock RpcClient + IDLParser for an active (not graduated) token."""
    state = _make_state(complete=False)
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64  # dummy bytes
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        yield rpc_instance, idl_instance


@pytest.fixture()
def _mock_rpc_graduated():
    """Mock RpcClient + IDLParser for a graduated token with pool data."""
    state = _make_state(complete=True)
    pool_info = {
        "pool_address": "PoolAddr123",
        "price_sol": 0.5,
        "base_reserves": 1000.0,
        "quote_reserves_sol": 500.0,
    }
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.info.get_pumpswap_info", new_callable=AsyncMock) as mock_ps,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        mock_ps.return_value = pool_info

        yield rpc_instance, idl_instance, mock_ps


def test_get_token_info_invalid_mint():
    """Invalid mint address returns error dict without making any RPC calls."""
    from pumpfun_cli.core.info import get_token_info

    result = asyncio.run(get_token_info("http://localhost:8899", "invalidmintaddress"))

    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]
    assert "hint" in result


def test_get_token_info_empty_mint():
    """Empty mint address returns error dict."""
    from pumpfun_cli.core.info import get_token_info

    result = asyncio.run(get_token_info("http://localhost:8899", ""))

    assert result["error"] == "invalid_address"
    assert "hint" in result


def test_get_token_info_not_found(_mock_rpc_not_found):
    """When RPC returns no account, result should have error='not_found'."""
    from pumpfun_cli.core.info import get_token_info

    result = asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    assert result["error"] == "not_found"
    assert MINT_STR in result["message"]


def test_get_token_info_active(_mock_rpc_active):
    """An active token on the bonding curve should return all expected fields."""
    from pumpfun_cli.core.info import get_token_info

    result = asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    expected_keys = {
        "mint",
        "bonding_curve",
        "price_sol",
        "bonding_progress",
        "graduated",
        "real_sol_reserves",
        "virtual_sol_reserves",
        "virtual_token_reserves",
        "creator",
        "is_mayhem_mode",
        "is_cashback_coin",
    }
    assert expected_keys.issubset(result.keys())
    assert result["graduated"] is False
    assert result["price_sol"] > 0
    assert "pool_address" not in result
    assert result["mint"] == MINT_STR


def test_get_token_info_graduated_with_pool(_mock_rpc_graduated):
    """A graduated token with pumpswap pool should include pool fields."""
    from pumpfun_cli.core.info import get_token_info

    result = asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    assert result["graduated"] is True
    assert result["pool_address"] == "PoolAddr123"
    assert result["base_reserves"] == 1000.0
    assert result["quote_reserves_sol"] == 500.0
    assert result["price_sol"] == 0.5


def test_get_token_info_passes_rpc_timeout():
    """When called with rpc_timeout=45.0, RpcClient should be constructed with timeout=45.0."""
    from pumpfun_cli.core.info import get_token_info

    state = _make_state(complete=False)
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        asyncio.run(get_token_info("http://localhost:8899", MINT_STR, rpc_timeout=45.0))

    MockRpc.assert_called_once_with("http://localhost:8899", timeout=45.0)


def test_get_token_info_graduated_pumpswap_timeout_surfaces_warning():
    """When get_pumpswap_info returns error, result has pumpswap_warning and pumpswap_error keys."""
    from pumpfun_cli.core.info import get_token_info

    state = _make_state(complete=True)
    pumpswap_err = {"error": "pumpswap_error", "message": "Request timed out"}
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.info.get_pumpswap_info", new_callable=AsyncMock) as mock_ps,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        mock_ps.return_value = pumpswap_err

        result = asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    assert result["graduated"] is True
    assert "pumpswap_warning" in result
    assert "pumpswap_error" in result
    assert result["price_sol"] > 0  # bonding curve price, not 0.0
    assert "pool_address" not in result


def test_get_token_info_graduated_pumpswap_no_pool_surfaces_warning():
    """'No PumpSwap pool found' error surfaces as warning."""
    from pumpfun_cli.core.info import get_token_info

    state = _make_state(complete=True)
    pumpswap_err = {"error": "pumpswap_error", "message": "No PumpSwap pool found for mint"}
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.info.get_pumpswap_info", new_callable=AsyncMock) as mock_ps,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        mock_ps.return_value = pumpswap_err

        result = asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    assert result["graduated"] is True
    assert "pumpswap_warning" in result
    assert "No PumpSwap pool" in result["pumpswap_warning"]
    assert "pool_address" not in result


def test_get_token_info_default_rpc_timeout_is_30():
    """Default RpcClient timeout should be 30.0 when no rpc_timeout passed."""
    from pumpfun_cli.core.info import get_token_info

    state = _make_state(complete=False)
    with (
        patch("pumpfun_cli.core.info.RpcClient") as MockRpc,
        patch("pumpfun_cli.core.info.IDLParser") as MockIDL,
    ):
        rpc_instance = AsyncMock()
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 64
        rpc_instance.get_account_info.return_value = resp
        MockRpc.return_value = rpc_instance

        idl_instance = MagicMock()
        idl_instance.decode_account_data.return_value = state
        MockIDL.return_value = idl_instance

        asyncio.run(get_token_info("http://localhost:8899", MINT_STR))

    MockRpc.assert_called_once_with("http://localhost:8899", timeout=30.0)
