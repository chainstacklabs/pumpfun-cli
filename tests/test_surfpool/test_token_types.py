"""Surfpool integration: buy/sell across all pump.fun token types.

Tests cover cashback tokens (bonding curve) to verify the sell instruction
correctly includes user_volume_accumulator in remaining accounts.

Standard and PumpSwap token types are already covered by test_trade.py
and test_pumpswap.py respectively. This file adds the missing types.

Ref: docs/token-types-test-matrix.md
"""

import pytest

from pumpfun_cli.core.trade import buy_token, sell_token

# ---------------------------------------------------------------------------
# Cashback token: bonding curve buy + sell
# The sell instruction must include user_volume_accumulator as a remaining
# account. If the cashback flag is not read properly, the on-chain program
# will reject the transaction.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_cashback_token(
    surfpool_rpc, funded_keypair, test_keystore, test_password, cashback_mint
):
    """BC-BUY-3: Buy a cashback-enabled token on the bonding curve."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=cashback_mint,
        sol_amount=0.001,
        slippage=25,
    )

    assert "error" not in result, f"Buy cashback token failed: {result}"
    assert result["action"] == "buy"
    assert result["tokens_received"] > 0
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_then_sell_cashback_token(
    surfpool_rpc, funded_keypair, test_keystore, test_password, cashback_mint
):
    """BC-SELL-3: Buy then sell a cashback token — sell must include volume accumulator."""
    buy_result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=cashback_mint,
        sol_amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=cashback_mint,
        amount_str="all",
        slippage=25,
    )
    assert "error" not in sell_result, f"Sell cashback token failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["sol_received"] > 0


# ---------------------------------------------------------------------------
# Token type detection: verify the bonding curve state flags are read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cashback_token_dry_run(
    surfpool_rpc, funded_keypair, test_keystore, test_password, cashback_mint
):
    """Dry-run on cashback token returns simulation without error."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=cashback_mint,
        sol_amount=0.001,
        slippage=25,
        dry_run=True,
    )

    assert "error" not in result, f"Dry-run failed: {result}"
    assert result["dry_run"] is True
    assert result["expected_tokens"] > 0
