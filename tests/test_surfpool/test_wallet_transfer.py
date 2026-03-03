"""Surfpool integration: wallet transfer including token transfer."""

import pytest

from pumpfun_cli.core.trade import buy_token
from pumpfun_cli.core.wallet import transfer_sol, transfer_token


@pytest.mark.asyncio
async def test_transfer_sol_with_confirm(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Transfer SOL with --confirm flag."""
    from solders.keypair import Keypair

    recipient = str(Keypair().pubkey())
    result = await transfer_sol(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        recipient_str=recipient,
        sol_amount=0.001,
        confirm=True,
    )
    assert "error" not in result, f"Transfer failed: {result}"
    assert result["action"] == "transfer"
    assert result["confirmed"] is True
    assert result["sol_amount"] == 0.001


@pytest.mark.asyncio
async def test_transfer_token_no_tokens(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Transferring tokens when wallet has none returns no_tokens error."""
    from solders.keypair import Keypair

    recipient = str(Keypair().pubkey())
    fake_mint = "CPLTbYbtDMKZtHBaPqdDmHjxNwESCEB14gm6VuoDpump"  # any valid mint
    result = await transfer_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        recipient_str=recipient,
        mint_str=fake_mint,
        amount_str="all",
    )
    assert result["error"] == "no_tokens"


@pytest.mark.asyncio
async def test_buy_then_transfer_token(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy tokens then transfer them to another wallet."""
    from solders.keypair import Keypair

    # Buy first
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

    # Transfer half
    recipient = str(Keypair().pubkey())
    tokens_bought = buy_result["tokens_received"]
    half = str(tokens_bought / 2)

    result = await transfer_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        recipient_str=recipient,
        mint_str=active_mint,
        amount_str=half,
    )
    assert "error" not in result, f"Transfer failed: {result}"
    assert result["action"] == "transfer_token"
    assert result["mint"] == active_mint
    assert result["amount"] > 0
    assert result["signature"]
