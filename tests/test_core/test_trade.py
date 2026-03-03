"""Tests for core/trade.py — mock RPC to test buy/sell/extras logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM

_PATCH_TOKEN_PROG = patch(
    "pumpfun_cli.core.trade.get_token_program_id",
    new=AsyncMock(return_value=TOKEN_2022_PROGRAM),
)

from pumpfun_cli.core.trade import (
    buy_token,
    claim_cashback,
    close_volume_accumulator,
    collect_creator_fees,
    migrate_token,
    sell_token,
)


@pytest.fixture
def mock_keypair():
    from solders.keypair import Keypair

    return Keypair()


@pytest.fixture
def tmp_keystore(tmp_path, mock_keypair):
    from pumpfun_cli.crypto import encrypt_keypair

    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(mock_keypair, "testpass", keyfile)
    return str(keyfile)


# --- invalid mint tests ---


@pytest.mark.asyncio
async def test_buy_token_invalid_mint(tmp_keystore):
    """Invalid mint returns error dict without RPC calls."""
    result = await buy_token(
        "http://rpc",
        tmp_keystore,
        "testpass",
        "invalidmintaddress",
        0.01,
    )
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


@pytest.mark.asyncio
async def test_sell_token_invalid_mint(tmp_keystore):
    """Invalid mint returns error dict without RPC calls."""
    result = await sell_token(
        "http://rpc",
        tmp_keystore,
        "testpass",
        "invalidmintaddress",
        "all",
    )
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


@pytest.mark.asyncio
async def test_migrate_token_invalid_mint(tmp_keystore):
    """Invalid mint returns error dict without RPC calls."""
    result = await migrate_token(
        "http://rpc",
        tmp_keystore,
        "testpass",
        "invalidmintaddress",
    )
    assert result["error"] == "invalid_address"
    assert "invalidmintaddress" in result["message"]


# --- buy_token tests ---


@pytest.mark.asyncio
async def test_buy_token_not_found(tmp_keystore):
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient, _PATCH_TOKEN_PROG:
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = None
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_buy_token_graduated(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {"complete": True}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["error"] == "graduated"


@pytest.mark.asyncio
async def test_buy_token_success(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "fakesig123"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }
        idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["action"] == "buy"
    assert result["signature"] == "fakesig123"
    assert result["sol_spent"] == 0.01
    assert "explorer" in result


# --- sell_token tests ---


@pytest.mark.asyncio
async def test_sell_token_not_found(tmp_keystore):
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient, _PATCH_TOKEN_PROG:
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = None
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_sell_token_graduated(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {"complete": True}

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["error"] == "graduated"


@pytest.mark.asyncio
async def test_sell_token_no_tokens(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_token_account_balance.return_value = 0
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
        }

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "all",
        )

    assert result["error"] == "no_tokens"


@pytest.mark.asyncio
async def test_sell_token_success(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_token_account_balance.return_value = 1_000_000
        client.send_tx.return_value = "sellsig456"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
        }
        idl.get_instruction_discriminators.return_value = {"sell": b"\x00" * 8}

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1.0",
        )

    assert result["action"] == "sell"
    assert result["signature"] == "sellsig456"


# --- claim_cashback tests ---


@pytest.mark.asyncio
async def test_claim_cashback_success(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        client.send_tx.return_value = "cashbacksig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.get_instruction_discriminators.return_value = {"claim_cashback": b"\x00" * 8}

        result = await claim_cashback("http://rpc", tmp_keystore, "testpass")

    assert result["action"] == "claim_cashback"
    assert result["signature"] == "cashbacksig"


# --- close_volume_accumulator tests ---


@pytest.mark.asyncio
async def test_close_volume_accumulator_success(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        client.send_tx.return_value = "closesig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.get_instruction_discriminators.return_value = {
            "close_user_volume_accumulator": b"\x00" * 8
        }

        result = await close_volume_accumulator("http://rpc", tmp_keystore, "testpass")

    assert result["action"] == "close_volume_accumulator"
    assert result["signature"] == "closesig"


# --- migrate_token tests ---


@pytest.mark.asyncio
async def test_migrate_not_found(tmp_keystore):
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = None
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        result = await migrate_token(
            "http://rpc", tmp_keystore, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_migrate_not_complete(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {"complete": False}

        result = await migrate_token(
            "http://rpc", tmp_keystore, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["error"] == "not_complete"


@pytest.mark.asyncio
async def test_migrate_success(tmp_keystore):
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
    ):
        client = AsyncMock()
        MockClient.return_value = client

        # First call: bonding curve, second call: global account
        bc_resp = MagicMock()
        bc_resp.value = MagicMock()
        bc_resp.value.data = b"\x00" * 200
        global_resp = MagicMock()
        global_resp.value = MagicMock()
        global_resp.value.data = b"\x00" * 200
        client.get_account_info.side_effect = [bc_resp, global_resp]
        client.send_tx.return_value = "migratesig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        # First call decodes BondingCurve, second decodes Global
        idl.decode_account_data.side_effect = [
            {"complete": True},
            {"withdraw_authority": bytes(Pubkey.from_string("11111111111111111111111111111112"))},
        ]
        idl.get_instruction_discriminators.return_value = {"migrate": b"\x00" * 8}

        result = await migrate_token(
            "http://rpc", tmp_keystore, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["action"] == "migrate"
    assert result["signature"] == "migratesig"


# --- collect_creator_fees tests ---


@pytest.mark.asyncio
async def test_collect_creator_fees_no_fees(tmp_keystore):
    """When both vaults are empty, returns no_fees error."""
    with patch("pumpfun_cli.core.trade.RpcClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_balance.return_value = 0
        client.get_token_account_balance.return_value = 0
        client.close = AsyncMock()

        result = await collect_creator_fees(
            rpc_url="http://fake",
            keystore_path=str(tmp_keystore),
            password="testpass",
        )
    assert result["error"] == "no_fees"


# --- slippage and confirm tests ---


@pytest.mark.asyncio
async def test_buy_token_slippage_zero(tmp_keystore):
    """Buy with slippage=0 means min_tokens_out == tokens_out (no tolerance)."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "slippage0sig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }
        idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            slippage=0,
        )

    assert result["action"] == "buy"
    assert result["signature"] == "slippage0sig"
    # With slippage=0, min_tokens_out = tokens_out * 100/100 = tokens_out exactly
    # Verify send_tx was actually called (transaction was submitted)
    client.send_tx.assert_called_once()


@pytest.mark.asyncio
async def test_sell_token_slippage_propagation(tmp_keystore):
    """Sell with slippage=0 vs slippage=50 should produce different min_sol values
    passed to build_sell_instructions."""
    captured_min_sols = []

    for slippage_val in (0, 50):
        with (
            patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
            patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
            patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build_sell,
            _PATCH_TOKEN_PROG,
        ):
            client = AsyncMock()
            MockClient.return_value = client
            resp = MagicMock()
            resp.value = MagicMock()
            resp.value.data = b"\x00" * 200
            client.get_account_info.return_value = resp
            client.get_token_account_balance.return_value = 1_000_000
            client.send_tx.return_value = "sellsig"
            client.close = AsyncMock()

            idl = MagicMock()
            MockIDL.return_value = idl
            idl.decode_account_data.return_value = {
                "complete": False,
                "virtual_token_reserves": 1_000_000_000_000,
                "virtual_sol_reserves": 30_000_000_000,
                "real_sol_reserves": 10_000_000_000,
                "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
                "is_mayhem_mode": False,
                "is_cashback_coin": False,
            }
            idl.get_instruction_discriminators.return_value = {"sell": b"\x00" * 8}
            mock_build_sell.return_value = []

            await sell_token(
                "http://rpc",
                tmp_keystore,
                "testpass",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "1.0",
                slippage=slippage_val,
            )

            call_kwargs = mock_build_sell.call_args
            captured_min_sols.append(
                call_kwargs.kwargs.get("min_sol_output", call_kwargs[1].get("min_sol_output"))
                if call_kwargs.kwargs
                else call_kwargs[1]["min_sol_output"]
            )

    # slippage=0 should give a higher min_sol than slippage=50
    assert captured_min_sols[0] > captured_min_sols[1]


@pytest.mark.asyncio
async def test_sell_token_partial_specific_amount(tmp_keystore):
    """Sell a specific token amount (not 'all'), verify it parses to int(500000 * 10**6)."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        patch("pumpfun_cli.core.trade.build_sell_instructions") as mock_build_sell,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        # Balance check now queries token balance for specific amounts
        client.get_token_account_balance.return_value = 500_000_000_000_000
        client.send_tx.return_value = "partialsig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
        }
        idl.get_instruction_discriminators.return_value = {"sell": b"\x00" * 8}
        mock_build_sell.return_value = []

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "500000",
        )

    assert result["action"] == "sell"
    # 500000 * 10**6 = 500_000_000_000 raw token units
    expected_amount = int(500000 * 10**6)
    call_kwargs = mock_build_sell.call_args
    actual_amount = (
        call_kwargs.kwargs.get("token_amount")
        if call_kwargs.kwargs
        else call_kwargs[1]["token_amount"]
    )
    assert actual_amount == expected_amount
    # get_token_account_balance is now called once for balance validation
    client.get_token_account_balance.assert_called_once()


@pytest.mark.asyncio
async def test_buy_token_without_confirm(tmp_keystore):
    """Buy without confirm flag — result should NOT have 'confirmed' key."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "noconfirmsig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }
        idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            confirm=False,
        )

    assert result["action"] == "buy"
    assert "confirmed" not in result


@pytest.mark.asyncio
async def test_buy_token_with_confirm(tmp_keystore):
    """Buy with confirm=True — result should have 'confirmed': True."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "confirmsig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }
        idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            confirm=True,
        )

    assert result["action"] == "buy"
    assert result["confirmed"] is True
    assert result["signature"] == "confirmsig"
    # Verify confirm=True was passed to send_tx
    client.send_tx.assert_called_once()
    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("confirm") is True or (
        len(call_kwargs.args) > 2 and call_kwargs.args[2] is True
    )


# --- dry-run tests ---


@pytest.mark.asyncio
async def test_buy_token_dry_run(tmp_keystore):
    """dry_run=True returns simulation dict without calling send_tx."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["action"] == "buy"
    assert result["venue"] == "bonding_curve"
    assert result["sol_in"] == 0.01
    assert result["expected_tokens"] > 0
    assert result["effective_price_sol"] > 0
    assert result["spot_price_sol"] > 0
    assert "price_impact_pct" in result
    assert "min_tokens_out" in result
    assert "signature" not in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_sell_token_dry_run(tmp_keystore):
    """dry_run=True returns simulation dict without calling send_tx."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_token_account_balance.return_value = 1_000_000
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
        }

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1.0",
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["action"] == "sell"
    assert result["venue"] == "bonding_curve"
    assert result["tokens_in"] == 1.0
    assert result["expected_sol"] > 0
    assert result["effective_price_sol"] > 0
    assert result["spot_price_sol"] > 0
    assert "price_impact_pct" in result
    assert "min_sol_out" in result
    assert "signature" not in result
    client.send_tx.assert_not_called()


# --- wrong password ---


# --- priority_fee / compute_units override tests ---


@pytest.mark.asyncio
async def test_buy_token_custom_priority_fee(tmp_keystore):
    """Custom priority_fee and compute_units are forwarded to send_tx."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000
        client.send_tx.return_value = "sig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }

        await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
            priority_fee=999_999,
            compute_units=150_000,
        )

    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 999_999
    assert call_kwargs.kwargs.get("compute_units") == 150_000


@pytest.mark.asyncio
async def test_sell_token_custom_priority_fee(tmp_keystore):
    """Custom priority_fee and compute_units are forwarded to send_tx for sell."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_token_account_balance.return_value = 1_000_000
        client.send_tx.return_value = "sig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
        }

        idl.get_instruction_discriminators.return_value = {"sell": b"\x00" * 8}

        await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1.0",
            priority_fee=42_000,
            compute_units=200_000,
        )

    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 42_000
    assert call_kwargs.kwargs.get("compute_units") == 200_000


@pytest.mark.asyncio
async def test_migrate_custom_priority_fee(tmp_keystore):
    """Custom priority_fee and compute_units are forwarded to send_tx for migrate."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        bc_resp = MagicMock()
        bc_resp.value = MagicMock()
        bc_resp.value.data = b"\x00" * 200
        global_resp = MagicMock()
        global_resp.value = MagicMock()
        global_resp.value.data = b"\x00" * 200
        client.get_account_info.side_effect = [bc_resp, global_resp]
        client.send_tx.return_value = "migsig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.side_effect = [
            {"complete": True},
            {"withdraw_authority": bytes(Pubkey.from_string("11111111111111111111111111111112"))},
        ]
        idl.get_instruction_discriminators.return_value = {"migrate": b"\x00" * 8}

        await migrate_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            priority_fee=77_000,
            compute_units=500_000,
        )

    call_kwargs = client.send_tx.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 77_000
    assert call_kwargs.kwargs.get("compute_units") == 500_000


@pytest.mark.asyncio
async def test_buy_wrong_password(tmp_keystore):
    with pytest.raises(ValueError, match="password"):
        await buy_token(
            "http://rpc",
            tmp_keystore,
            "wrongpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )


# --- pre-trade balance validation tests ---


@pytest.mark.asyncio
async def test_buy_token_insufficient_sol(tmp_keystore):
    """Buy with wallet balance too low returns insufficient_balance without calling send_tx."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 1_000  # very low balance
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }

        result = await buy_token(
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
async def test_sell_token_insufficient_tokens(tmp_keystore):
    """Sell a specific amount exceeding token balance returns insufficient_balance."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_token_account_balance.return_value = 500_000  # 0.5 tokens at 6 decimals
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
        }

        result = await sell_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1000",  # asking to sell 1000 tokens but only have 0.5
        )

    assert result["error"] == "insufficient_balance"
    assert "available_tokens" in result
    assert "required_tokens" in result
    client.send_tx.assert_not_called()


@pytest.mark.asyncio
async def test_buy_token_sufficient_sol_proceeds(tmp_keystore):
    """Buy with adequate balance proceeds normally (regression guard)."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 10_000_000_000  # 10 SOL — plenty
        client.send_tx.return_value = "sufficientsig"
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }
        idl.get_instruction_discriminators.return_value = {"buy": b"\x00" * 8}

        result = await buy_token(
            "http://rpc",
            tmp_keystore,
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            0.01,
        )

    assert result["action"] == "buy"
    assert result["signature"] == "sufficientsig"
    client.send_tx.assert_called_once()


@pytest.mark.asyncio
async def test_buy_token_dry_run_insufficient_sol_includes_warning(tmp_keystore):
    """Dry-run with low balance still returns simulation but includes balance_warning."""
    with (
        patch("pumpfun_cli.core.trade.RpcClient") as MockClient,
        patch("pumpfun_cli.core.trade.IDLParser") as MockIDL,
        _PATCH_TOKEN_PROG,
    ):
        client = AsyncMock()
        MockClient.return_value = client
        resp = MagicMock()
        resp.value = MagicMock()
        resp.value.data = b"\x00" * 200
        client.get_account_info.return_value = resp
        client.get_balance.return_value = 1_000  # very low
        client.close = AsyncMock()

        idl = MagicMock()
        MockIDL.return_value = idl
        idl.decode_account_data.return_value = {
            "complete": False,
            "virtual_token_reserves": 1_000_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "real_sol_reserves": 10_000_000_000,
            "creator": bytes(Pubkey.from_string("11111111111111111111111111111112")),
            "is_mayhem_mode": False,
        }

        result = await buy_token(
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
