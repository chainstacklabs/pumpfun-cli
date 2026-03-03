"""Surfpool integration: buy and sell against forked mainnet state."""

import pytest

from pumpfun_cli.core.trade import buy_token, sell_token


@pytest.mark.asyncio
async def test_buy_token(surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint):
    """Buy a small amount of tokens on the surfpool fork."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        sol_amount=0.001,
        slippage=25,
    )

    assert "error" not in result, f"Buy failed: {result}"
    assert result["action"] == "buy"
    assert result["mint"] == active_mint
    assert result["sol_spent"] == 0.001
    assert result["tokens_received"] > 0
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_then_sell(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy tokens then sell them all back."""
    # Buy
    buy_result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        sol_amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # Sell all
    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount_str="all",
        slippage=25,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["sol_received"] > 0
    assert sell_result["signature"]


@pytest.mark.asyncio
async def test_buy_with_confirm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy with --confirm flag waits for confirmation."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        sol_amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in result, f"Buy failed: {result}"
    assert result["confirmed"] is True
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_graduated_token_fails(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """Buying a graduated token via bonding curve returns graduated error."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=25,
    )
    assert result["error"] == "graduated"


@pytest.mark.asyncio
async def test_buy_then_partial_sell(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy tokens then sell a specific amount (not all)."""
    buy_result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        sol_amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # Sell half the tokens
    half_tokens = buy_result["tokens_received"] / 2
    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount_str=str(half_tokens),
        slippage=25,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["signature"]


@pytest.mark.asyncio
async def test_buy_without_confirm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy without --confirm returns signature but no confirmed key."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        sol_amount=0.001,
        slippage=25,
        confirm=False,
    )
    assert "error" not in result, f"Buy failed: {result}"
    assert result["signature"]
    assert "confirmed" not in result
