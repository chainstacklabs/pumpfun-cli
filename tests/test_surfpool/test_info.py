"""Surfpool integration: info command — reads bonding curve state from forked mainnet."""

import pytest

from pumpfun_cli.core.info import get_token_info


@pytest.mark.asyncio
async def test_get_token_info(surfpool_rpc, active_mint):
    """Fetch real bonding curve state via surfpool fork."""
    result = await get_token_info(surfpool_rpc, active_mint)

    assert "error" not in result, f"Unexpected error: {result}"
    assert result["mint"] == active_mint
    assert result["bonding_curve"]  # non-empty
    assert result["price_sol"] >= 0
    assert 0 <= result["bonding_progress"] <= 100
    assert isinstance(result["graduated"], bool)
    assert result["real_sol_reserves"] >= 0
    assert result["virtual_sol_reserves"] > 0
    assert result["virtual_token_reserves"] > 0


@pytest.mark.asyncio
async def test_info_not_found(surfpool_rpc):
    """Querying a fake mint returns not_found."""
    from solders.keypair import Keypair

    fake_mint = str(Keypair().pubkey())
    result = await get_token_info(surfpool_rpc, fake_mint)
    assert result["error"] == "not_found"
