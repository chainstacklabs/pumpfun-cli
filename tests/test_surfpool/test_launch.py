"""Surfpool integration: token launch with mayhem/cashback flag combinations.

Tests launch_token() against a surfpool fork, covering the full matrix of
is_mayhem x is_cashback (with and without initial buy), verifying that
tokens are created on-chain successfully.

The IPFS metadata upload is mocked — the on-chain program does not
validate URI content, so a fake URI is sufficient for testing the
create_v2 instruction serialisation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from pumpfun_cli.core.info import get_token_info
from pumpfun_cli.core.launch import launch_token

FAKE_URI = "https://example.com/test-metadata.json"

_UPLOAD_PATCH = patch(
    "pumpfun_cli.core.launch.upload_metadata",
    new_callable=AsyncMock,
    return_value=FAKE_URI,
)


# ── mayhem=False, cashback=False (default) ──────────────────────────────


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_default(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch with defaults: no mayhem, no cashback."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Default",
        ticker="DFLT",
        description="default launch",
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["action"] == "launch"
    assert result["is_cashback"] is False
    assert result["signature"]

    info = await get_token_info(surfpool_rpc, result["mint"])
    assert "error" not in info, f"Token not found: {info}"
    assert info["graduated"] is False


# ── mayhem=False, cashback=True ─────────────────────────────────────────


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_cashback(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch with cashback enabled, no mayhem."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Cashback",
        ticker="CSHB",
        description="cashback launch",
        is_cashback=True,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["is_cashback"] is True
    assert result["signature"]

    info = await get_token_info(surfpool_rpc, result["mint"])
    assert "error" not in info, f"Token not found: {info}"
    assert info["graduated"] is False


# ── mayhem=True, cashback=False ─────────────────────────────────────────


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_mayhem(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch with mayhem enabled, no cashback."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Mayhem",
        ticker="MYHM",
        description="mayhem launch",
        is_mayhem=True,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["is_cashback"] is False
    assert result["signature"]

    info = await get_token_info(surfpool_rpc, result["mint"])
    assert "error" not in info, f"Token not found: {info}"
    assert info["graduated"] is False


# ── mayhem=True, cashback=True ──────────────────────────────────────────


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_mayhem_cashback(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch with both mayhem and cashback enabled."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="MayhemCB",
        ticker="MHCB",
        description="mayhem + cashback launch",
        is_mayhem=True,
        is_cashback=True,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["is_cashback"] is True
    assert result["signature"]

    info = await get_token_info(surfpool_rpc, result["mint"])
    assert "error" not in info, f"Token not found: {info}"
    assert info["graduated"] is False


# ── with initial buy ────────────────────────────────────────────────────


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_default_with_buy(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch with initial buy, no mayhem, no cashback."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="DefBuy",
        ticker="DBUY",
        description="default + buy",
        initial_buy_sol=0.001,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["initial_buy_sol"] == 0.001
    assert result["signature"]


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_cashback_with_buy(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch cashback token with initial buy."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="CashBuy",
        ticker="CBUY",
        description="cashback + buy",
        is_cashback=True,
        initial_buy_sol=0.001,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["is_cashback"] is True
    assert result["initial_buy_sol"] == 0.001
    assert result["signature"]


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_mayhem_with_buy(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch mayhem token with initial buy."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="MyhBuy",
        ticker="MBUY",
        description="mayhem + buy",
        is_mayhem=True,
        initial_buy_sol=0.001,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["initial_buy_sol"] == 0.001
    assert result["signature"]


@pytest.mark.asyncio
@_UPLOAD_PATCH
async def test_launch_mayhem_cashback_with_buy(
    _mock_upload, surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch mayhem + cashback token with initial buy."""
    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="MhCbBuy",
        ticker="MCBB",
        description="mayhem + cashback + buy",
        is_mayhem=True,
        is_cashback=True,
        initial_buy_sol=0.001,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["is_cashback"] is True
    assert result["initial_buy_sol"] == 0.001
    assert result["signature"]
