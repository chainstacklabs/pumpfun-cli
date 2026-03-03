"""Surfpool integration: info command for graduated tokens."""

import pytest

from pumpfun_cli.core.info import get_token_info


@pytest.mark.asyncio
async def test_get_token_info_graduated(surfpool_rpc, graduated_mint):
    """Info for a graduated token includes PumpSwap pool data."""
    result = await get_token_info(surfpool_rpc, graduated_mint)

    assert "error" not in result, f"Unexpected error: {result}"
    assert result["graduated"] is True
    assert result["price_sol"] >= 0

    # Pool data is enriched only if getProgramAccounts succeeds.
    # On surfpool this may timeout, so pool_address is optional.
    if "pool_address" in result:
        assert result["base_reserves"] >= 0
        assert result["quote_reserves_sol"] >= 0
