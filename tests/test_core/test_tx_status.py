"""Unit tests for pumpfun_cli.core.tx_status module."""

import asyncio
from unittest.mock import AsyncMock, patch

# A valid-looking base58 signature (64 bytes = 88 base58 chars).
_FAKE_SIG = (
    "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQU"
)


def test_invalid_signature_format():
    """Non-base58 string returns invalid_signature error."""
    from pumpfun_cli.core.tx_status import get_tx_status

    result = asyncio.run(get_tx_status("http://localhost:8899", "not-a-valid-sig!!!"))

    assert result["error"] == "invalid_signature"
    assert "Invalid" in result["message"]


def test_transaction_not_found():
    """When RPC returns None, result should have error='not_found'."""
    from pumpfun_cli.core.tx_status import get_tx_status

    with patch("pumpfun_cli.core.tx_status.RpcClient") as MockRpc:
        instance = AsyncMock()
        instance.get_transaction.return_value = None
        MockRpc.return_value = instance

        result = asyncio.run(get_tx_status("http://localhost:8899", _FAKE_SIG))

    assert result["error"] == "not_found"
    assert _FAKE_SIG in result["message"]


def test_confirmed_transaction():
    """A confirmed transaction returns status='confirmed' with correct fields."""
    from pumpfun_cli.core.tx_status import get_tx_status

    with patch("pumpfun_cli.core.tx_status.RpcClient") as MockRpc:
        instance = AsyncMock()
        instance.get_transaction.return_value = {
            "slot": 12345,
            "err": None,
            "fee": 5000,
            "block_time": 1700000000,
        }
        MockRpc.return_value = instance

        result = asyncio.run(get_tx_status("http://localhost:8899", _FAKE_SIG))

    assert result["status"] == "confirmed"
    assert result["slot"] == 12345
    assert result["fee_lamports"] == 5000
    assert result["fee_sol"] == 5000 / 1_000_000_000
    assert result["block_time"] == 1700000000
    assert result["signature"] == _FAKE_SIG
    assert "error" not in result
    assert "explorer" in result


def test_failed_transaction():
    """A failed transaction returns status='failed' with error key."""
    from pumpfun_cli.core.tx_status import get_tx_status

    with patch("pumpfun_cli.core.tx_status.RpcClient") as MockRpc:
        instance = AsyncMock()
        instance.get_transaction.return_value = {
            "slot": 12345,
            "err": {"InstructionError": [0, "Custom(1)"]},
            "fee": 5000,
            "block_time": 1700000000,
        }
        MockRpc.return_value = instance

        result = asyncio.run(get_tx_status("http://localhost:8899", _FAKE_SIG))

    assert result["status"] == "failed"
    assert "error" in result
    assert result["error"] == {"InstructionError": [0, "Custom(1)"]}


def test_client_closed_on_success():
    """Client.close() is awaited on success."""
    from pumpfun_cli.core.tx_status import get_tx_status

    with patch("pumpfun_cli.core.tx_status.RpcClient") as MockRpc:
        instance = AsyncMock()
        instance.get_transaction.return_value = {
            "slot": 12345,
            "err": None,
            "fee": 5000,
            "block_time": 1700000000,
        }
        MockRpc.return_value = instance

        asyncio.run(get_tx_status("http://localhost:8899", _FAKE_SIG))

    instance.close.assert_awaited_once()


def test_client_closed_on_not_found():
    """Client.close() is awaited even when transaction is not found."""
    from pumpfun_cli.core.tx_status import get_tx_status

    with patch("pumpfun_cli.core.tx_status.RpcClient") as MockRpc:
        instance = AsyncMock()
        instance.get_transaction.return_value = None
        MockRpc.return_value = instance

        asyncio.run(get_tx_status("http://localhost:8899", _FAKE_SIG))

    instance.close.assert_awaited_once()
