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

_LAUNCH_MATRIX = [
    pytest.param(False, False, None, id="default"),
    pytest.param(False, True, None, id="cashback"),
    pytest.param(True, False, None, id="mayhem"),
    pytest.param(True, True, None, id="mayhem+cashback"),
    pytest.param(False, False, 0.001, id="default+buy"),
    pytest.param(False, True, 0.001, id="cashback+buy"),
    pytest.param(True, False, 0.001, id="mayhem+buy"),
    pytest.param(True, True, 0.001, id="mayhem+cashback+buy"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("is_mayhem,is_cashback,initial_buy_sol", _LAUNCH_MATRIX)
@_UPLOAD_PATCH
async def test_launch(
    _mock_upload,
    surfpool_rpc,
    funded_keypair,
    test_keystore,
    test_password,
    is_mayhem,
    is_cashback,
    initial_buy_sol,
):
    """Launch token with given mayhem/cashback/buy combination."""
    kwargs = {}
    if is_mayhem:
        kwargs["is_mayhem"] = True
    if is_cashback:
        kwargs["is_cashback"] = True
    if initial_buy_sol is not None:
        kwargs["initial_buy_sol"] = initial_buy_sol

    result = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Test",
        ticker="TST",
        description="parametrized launch",
        **kwargs,
    )

    assert "error" not in result, f"Launch failed: {result}"
    assert result["action"] == "launch"
    assert result["is_cashback"] is is_cashback
    assert result["signature"]

    if initial_buy_sol is not None:
        assert result["initial_buy_sol"] == initial_buy_sol

    info = await get_token_info(surfpool_rpc, result["mint"])
    assert "error" not in info, f"Token not found: {info}"
    assert info["graduated"] is False
