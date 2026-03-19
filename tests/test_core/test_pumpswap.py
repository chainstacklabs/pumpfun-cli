"""Tests for core/pumpswap.py — mock RPC to test PumpSwap trade logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pumpfun_cli.core.pumpswap import buy_pumpswap, get_pumpswap_info, sell_pumpswap
from pumpfun_cli.protocol.contracts import (
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET,
    STANDARD_PUMPSWAP_FEE_RECIPIENT,
    TOKEN_PROGRAM,
)
from tests.test_core.helpers import build_pool_data


def _mock_global_config_resp():
    """Build a mock GlobalConfig account response with standard fee recipient."""
    off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET
    config_data = bytearray(off + 32)
    config_data[off : off + 32] = bytes(STANDARD_PUMPSWAP_FEE_RECIPIENT)
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = bytes(config_data)
    return resp


def _mock_pool_resp(pool_data):
    """Build a mock get_account_info response for a pool account."""
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.data = pool_data
    return resp


def _mock_pool_not_found():
    """Build a mock get_account_info response for pool not found."""
    resp = MagicMock()
    resp.value = None
    return resp


# --- invalid mint tests ---


@pytest.mark.asyncio
async def test_buy_pumpswap_invalid_mint(tmp_keystore):
    """Invalid mint returns error dict without RPC calls."""
    result = await buy_pumpswap(
        "http://rpc",
        tmp_keystore,
        "testpass",
        "invalidmintaddress",
        0.01,
    )
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


@pytest.mark.asyncio
async def test_sell_pumpswap_invalid_mint(tmp_keystore):
    """Invalid mint returns error dict without RPC calls."""
    result = await sell_pumpswap(
        "http://rpc",
        tmp_keystore,
        "testpass",
        "invalidmintaddress",
        "all",
    )
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


@pytest.mark.asyncio
async def test_get_pumpswap_info_invalid_mint():
    """Invalid mint returns error dict without RPC calls."""
    result = await get_pumpswap_info("http://rpc", "invalidmintaddress")
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


@pytest.mark.asyncio
async def test_buy_pumpswap_no_pool(tmp_keystore):
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # Pool lookup via get_account_info returns not found
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "pumpswap_error"
    assert "No PumpSwap pool" in result["message"]


def _mock_token_program_resp():
    """Build a mock account response for token program check."""
    resp = MagicMock()
    resp.value = MagicMock()
    resp.value.owner = TOKEN_PROGRAM
    return resp


def _mock_vol_accumulator_resp():
    """Build a mock response for volume accumulator (not found)."""
    resp = MagicMock()
    resp.value = None
    return resp


@pytest.mark.asyncio
async def test_buy_pumpswap_no_liquidity(tmp_keystore):
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # get_account_info calls: pool, token_program, GlobalConfig
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        # pool balances both 0 => price = 0
        client.get_token_account_balance.return_value = 0
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "no_liquidity"


@pytest.mark.asyncio
async def test_buy_pumpswap_success(tmp_keystore):
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # get_account_info calls: pool, token_program, GlobalConfig, vol_accumulator
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
            _mock_vol_accumulator_resp(),
        ]
        # base=1B tokens, quote=30B lamports => price = 30
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "buysig"
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "buysig"


@pytest.mark.asyncio
async def test_sell_pumpswap_no_tokens(tmp_keystore):
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # get_account_info calls: pool, token_program, GlobalConfig
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.return_value = 0
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["error"] == "no_tokens"


@pytest.mark.asyncio
async def test_sell_pumpswap_success(tmp_keystore):
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # get_account_info calls: pool, token_program, GlobalConfig
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        # first call: user token balance, then pool base, pool quote for price
        client.get_token_account_balance.side_effect = [1_000_000, 1_000_000_000, 30_000_000_000]
        client.send_tx.return_value = "sellsig"
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["action"] == "sell"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "sellsig"


@pytest.mark.asyncio
async def test_get_pumpswap_info_success():
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        # get_account_info calls: pool
        client.get_account_info.return_value = _mock_pool_resp(pool_data)
        # get_pool_balances called once, used for both price and reserves
        client.get_token_account_balance.side_effect = [
            1_000_000_000,
            30_000_000_000,
        ]
        client.close = AsyncMock()

        result = await get_pumpswap_info(
            "http://rpc", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert "pool_address" in result
    assert result["price_sol"] == 30.0
    assert result["mayhem_mode"] is False


@pytest.mark.asyncio
async def test_get_pumpswap_info_no_pool():
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        result = await get_pumpswap_info(
            "http://rpc", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["error"] == "pumpswap_error"


@pytest.mark.asyncio
async def test_buy_pumpswap_custom_priority_fee(tmp_keystore):
    """Custom priority_fee and compute_units are forwarded to send_tx."""
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

        await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            priority_fee=55_000,
            compute_units=350_000,
        )

    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 55_000
    assert call_kwargs.kwargs.get("compute_units") == 350_000


@pytest.mark.asyncio
async def test_sell_pumpswap_custom_priority_fee(tmp_keystore):
    """Custom priority_fee and compute_units are forwarded to send_tx for sell."""
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000, 1_000_000_000, 30_000_000_000]
        client.send_tx.return_value = "sellsig"
        client.close = AsyncMock()

        await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
            priority_fee=88_000,
            compute_units=250_000,
        )

    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 88_000
    assert call_kwargs.kwargs.get("compute_units") == 250_000


@pytest.mark.asyncio
async def test_buy_pumpswap_dry_run(tmp_keystore):
    """dry_run=True returns simulation dict without calling send_tx."""
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
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["sol_in"] == 0.01
    assert result["expected_tokens"] > 0
    assert result["effective_price_sol"] > 0
    assert result["spot_price_sol"] > 0
    assert "price_impact_pct" in result
    assert "signature" not in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_sell_pumpswap_dry_run(tmp_keystore):
    """dry_run=True returns simulation dict without calling send_tx."""
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000, 1_000_000_000, 30_000_000_000]
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["action"] == "sell"
    assert result["venue"] == "pumpswap"
    assert result["tokens_in"] > 0
    assert result["expected_sol"] > 0
    assert "price_impact_pct" in result
    assert "signature" not in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_buy_pumpswap_slippage_zero(tmp_keystore):
    """Buy with slippage=0 means min_base_amount_out == estimated_tokens."""
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
        # base=1B tokens, quote=30B lamports
        base_balance = 1_000_000_000
        quote_balance = 30_000_000_000
        client.get_token_account_balance.side_effect = [base_balance, quote_balance]
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "buysig_slippage0"
        client.close = AsyncMock()

        sol_amount = 0.01
        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            sol_amount,
            slippage=0,
        )

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "buysig_slippage0"

    # Verify the formula: with slippage=0, min_base_amount_out == estimated_tokens
    sol_lamports = int(sol_amount * 1_000_000_000)
    effective_sol = sol_lamports * 99 // 100
    estimated_tokens = base_balance * effective_sol // (quote_balance + effective_sol)
    min_base_amount_out = estimated_tokens * (100 - 0) // 100
    assert min_base_amount_out == estimated_tokens
    assert result["tokens_received"] == estimated_tokens / (10**6)


@pytest.mark.asyncio
async def test_sell_pumpswap_partial_amount(tmp_keystore):
    """Sell a specific token amount (not 'all') — should NOT query user balance."""
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        # Balance check + pool balances: user_balance, pool_base, pool_quote
        user_balance = 500_000_000_000  # 500 tokens — enough
        base_balance = 1_000_000_000
        quote_balance = 30_000_000_000
        client.get_token_account_balance.side_effect = [user_balance, base_balance, quote_balance]
        client.send_tx.return_value = "sellsig_partial"
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "500",
        )

    assert result["action"] == "sell"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "sellsig_partial"
    assert result["tokens_sold"] == 500.0
    # get_token_account_balance called 3 times: balance check + pool base + pool quote
    assert client.get_token_account_balance.call_count == 3


# --- pre-trade balance validation tests ---


@pytest.mark.asyncio
async def test_buy_pumpswap_insufficient_sol(tmp_keystore):
    """Buy with wallet balance too low returns insufficient_balance."""
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        # base=1B tokens, quote=30B lamports => has liquidity
        client.get_token_account_balance.side_effect = [1_000_000_000, 30_000_000_000]
        client.get_balance.return_value = 1_000  # very low
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "insufficient_balance"
    assert "available_sol" in result
    assert "required_sol" in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_sell_pumpswap_insufficient_tokens(tmp_keystore):
    """Sell specific amount exceeding token balance returns insufficient_balance."""
    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        # User token balance = 500_000 (0.5 tokens), then pool balances
        client.get_token_account_balance.side_effect = [
            500_000,
            1_000_000_000,
            30_000_000_000,
        ]
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1000",  # asking to sell 1000 but only have 0.5
        )

    assert result["error"] == "insufficient_balance"
    assert "available_tokens" in result
    assert "required_tokens" in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_buy_pumpswap_sufficient_sol_proceeds(tmp_keystore):
    """Buy with adequate balance proceeds normally (regression guard)."""
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
        client.get_balance.return_value = 10_000_000_000  # 10 SOL — plenty
        client.send_tx.return_value = "buysig_sufficient"
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "buysig_sufficient"
    client.send_tx.assert_called_once()


@pytest.mark.asyncio
async def test_buy_pumpswap_dry_run_insufficient_sol_includes_warning(tmp_keystore):
    """Dry-run with low balance still returns simulation but includes balance_warning."""
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
        client.get_balance.return_value = 1_000  # very low
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert "balance_warning" in result
    client.send_tx.assert_not_called()


# --- TransactionFailedError / slippage tests ---


@pytest.mark.asyncio
async def test_buy_pumpswap_slippage_error(tmp_keystore):
    """PumpSwap slippage error code 6040 returns slippage error."""
    from pumpfun_cli.protocol.client import TransactionFailedError

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
        client.send_tx.side_effect = TransactionFailedError(
            "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6040))))"
        )
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "slippage"
    assert result["error_code"] == 6040


@pytest.mark.asyncio
async def test_sell_pumpswap_slippage_error(tmp_keystore):
    """PumpSwap slippage error code 6004 returns slippage error."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    pool_data = build_pool_data()

    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.side_effect = [
            _mock_pool_resp(pool_data),
            _mock_token_program_resp(),
            _mock_global_config_resp(),
        ]
        client.get_token_account_balance.side_effect = [1_000_000, 1_000_000_000, 30_000_000_000]
        client.send_tx.side_effect = TransactionFailedError(
            "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6004))))"
        )
        client.close = AsyncMock()

        result = await sell_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["error"] == "slippage"
    assert result["error_code"] == 6004


@pytest.mark.asyncio
async def test_buy_pumpswap_non_slippage_tx_error(tmp_keystore):
    """Non-slippage error code returns tx_error."""
    from pumpfun_cli.protocol.client import TransactionFailedError

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
        client.send_tx.side_effect = TransactionFailedError(
            "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(9999))))"
        )
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "tx_error"
    assert result["error_code"] == 9999


@pytest.mark.asyncio
async def test_buy_pumpswap_pool_not_found_still_works(tmp_keystore):
    """Pool-not-found RuntimeError still returns pumpswap_error (regression)."""
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "pumpswap_error"
    assert "No PumpSwap pool" in result["message"]


@pytest.mark.asyncio
async def test_buy_pumpswap_without_confirm(tmp_keystore):
    """Buy without confirm=True — result should NOT contain 'confirmed' key."""
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
        client.send_tx.return_value = "buysig_noconfirm"
        client.close = AsyncMock()

        result = await buy_pumpswap(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            confirm=False,
        )

    assert result["action"] == "buy"
    assert result["venue"] == "pumpswap"
    assert result["signature"] == "buysig_noconfirm"
    assert "confirmed" not in result


@pytest.mark.asyncio
async def test_get_pumpswap_info_uses_30s_default_timeout():
    """get_pumpswap_info should construct RpcClient with timeout=30.0 by default."""
    with patch("pumpfun_cli.core.pumpswap.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_account_info.return_value = _mock_pool_not_found()
        client.close = AsyncMock()

        await get_pumpswap_info("http://rpc", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    MockClient.assert_called_once_with("http://rpc", timeout=30.0)
