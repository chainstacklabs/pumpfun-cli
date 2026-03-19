"""Surfpool integration: PumpSwap AMM buy/sell against forked mainnet state.

Pool lookup now uses PDA derivation + getAccountInfo (not getProgramAccounts),
so there is no heavy account scan. The timeout is kept at 120s for general
surfpool lazy-loading of pool token accounts from mainnet.
"""

import pytest

from pumpfun_cli.core.pumpswap import buy_pumpswap, get_pumpswap_info, sell_pumpswap

# Surfpool needs time to lazy-fetch pool token accounts from mainnet.
SURFPOOL_TIMEOUT = 120.0


@pytest.mark.asyncio
async def test_get_pumpswap_info(surfpool_rpc, graduated_mint):
    """Fetch PumpSwap pool info for a graduated token."""
    result = await get_pumpswap_info(surfpool_rpc, graduated_mint, rpc_timeout=SURFPOOL_TIMEOUT)

    assert "error" not in result, f"Unexpected error: {result}"
    assert result["pool_address"]
    assert result["price_sol"] > 0
    assert result["base_reserves"] >= 0
    assert result["quote_reserves_sol"] >= 0
    assert isinstance(result["mayhem_mode"], bool)


@pytest.mark.asyncio
async def test_buy_pumpswap(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """Buy tokens via PumpSwap AMM on surfpool fork."""
    result = await buy_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=25,
        rpc_timeout=SURFPOOL_TIMEOUT,
    )

    assert "error" not in result, f"Buy failed: {result}"
    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["mint"] == graduated_mint
    assert result["sol_spent"] == 0.001
    assert result["tokens_received"] > 0
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_then_sell_pumpswap(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """Buy tokens via PumpSwap then sell them all back."""
    # Buy
    buy_result = await buy_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # Sell all
    sell_result = await sell_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        amount_str="all",
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["venue"] == "pumpswap"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["sol_received"] > 0
    assert sell_result["signature"]


@pytest.mark.asyncio
async def test_buy_then_partial_sell_pumpswap(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """Buy via PumpSwap then sell a specific amount (not all)."""
    buy_result = await buy_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    half_tokens = buy_result["tokens_received"] / 2
    sell_result = await sell_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        amount_str=str(half_tokens),
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["venue"] == "pumpswap"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["signature"]
