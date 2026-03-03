"""Tests for tx-status command."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()

_FAKE_SIG = (
    "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQU"
)


def test_tx_status_no_rpc_exits_1(tmp_path, monkeypatch):
    """Without RPC configured, tx-status should exit 1 mentioning RPC."""
    monkeypatch.delenv("PUMPFUN_RPC", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["tx-status", _FAKE_SIG])
    assert result.exit_code == 1
    assert "RPC" in result.output or "rpc" in result.output


def test_tx_status_invalid_signature_exits_1():
    """Invalid signature error from core returns exit 1."""
    with patch("pumpfun_cli.commands.tx_status.get_tx_status") as mock:
        mock.return_value = {
            "error": "invalid_signature",
            "message": "Invalid transaction signature. Must be a base58-encoded 64-byte signature.",
        }
        result = runner.invoke(app, ["--rpc", "http://rpc", "tx-status", "bad-sig"])

    assert result.exit_code == 1
    assert "Invalid" in result.output


def test_tx_status_not_found_exits_1():
    """Not-found error from core returns exit 1."""
    with patch("pumpfun_cli.commands.tx_status.get_tx_status") as mock:
        mock.return_value = {
            "error": "not_found",
            "message": f"Transaction {_FAKE_SIG} not found on-chain.",
        }
        result = runner.invoke(app, ["--rpc", "http://rpc", "tx-status", _FAKE_SIG])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_tx_status_confirmed_json():
    """Confirmed transaction with --json outputs proper JSON."""
    with patch("pumpfun_cli.commands.tx_status.get_tx_status") as mock:
        mock.return_value = {
            "signature": _FAKE_SIG,
            "status": "confirmed",
            "slot": 12345,
            "block_time": 1700000000,
            "fee_lamports": 5000,
            "fee_sol": 0.000005,
            "explorer": f"https://solscan.io/tx/{_FAKE_SIG}",
        }
        result = runner.invoke(app, ["--json", "--rpc", "http://rpc", "tx-status", _FAKE_SIG])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "confirmed"
    assert data["slot"] == 12345
    assert "explorer" in data


def test_tx_status_failed_json():
    """Failed transaction with --json outputs status='failed'."""
    with patch("pumpfun_cli.commands.tx_status.get_tx_status") as mock:
        mock.return_value = {
            "signature": _FAKE_SIG,
            "status": "failed",
            "slot": 12345,
            "block_time": 1700000000,
            "fee_lamports": 5000,
            "fee_sol": 0.000005,
            "error": {"InstructionError": [0, "Custom(1)"]},
            "explorer": f"https://solscan.io/tx/{_FAKE_SIG}",
        }
        result = runner.invoke(app, ["--json", "--rpc", "http://rpc", "tx-status", _FAKE_SIG])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "failed"
    assert "error" in data


def test_tx_status_human_output():
    """Without --json, human-readable output contains key fields."""
    with patch("pumpfun_cli.commands.tx_status.get_tx_status") as mock:
        mock.return_value = {
            "signature": _FAKE_SIG,
            "status": "confirmed",
            "slot": 12345,
            "block_time": 1700000000,
            "fee_lamports": 5000,
            "fee_sol": 0.000005,
            "explorer": f"https://solscan.io/tx/{_FAKE_SIG}",
        }
        result = runner.invoke(app, ["--rpc", "http://rpc", "tx-status", _FAKE_SIG])

    assert result.exit_code == 0
    output = result.output
    assert "confirmed" in output
    assert "12345" in output
    assert _FAKE_SIG in output
