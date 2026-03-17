"""Tests for trade commands — buy, sell, claim-cashback, close-volume-acc, migrate."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()

# A valid base58 Solana pubkey for use in tests that need to pass mint validation.
_FAKE_MINT = "11111111111111111111111111111111"


def test_buy_no_rpc_exits_1():
    result = runner.invoke(app, ["buy", _FAKE_MINT, "0.1"])
    assert result.exit_code == 1
    assert "RPC" in result.output or "rpc" in result.output or "Password" in result.output


def test_sell_no_rpc_exits_1():
    result = runner.invoke(app, ["sell", _FAKE_MINT, "all"])
    assert result.exit_code == 1


def test_claim_cashback_no_rpc_exits_1():
    result = runner.invoke(app, ["claim-cashback"])
    assert result.exit_code == 1


def test_close_volume_acc_no_rpc_exits_1():
    result = runner.invoke(app, ["close-volume-acc"])
    assert result.exit_code == 1


def test_collect_creator_fee_no_rpc_exits_1():
    result = runner.invoke(app, ["collect-creator-fee"])
    assert result.exit_code != 0


def test_migrate_no_rpc_exits_1():
    result = runner.invoke(app, ["migrate", _FAKE_MINT])
    assert result.exit_code == 1


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_buy_with_force_amm_flag_help():
    result = runner.invoke(app, ["buy", "--help"])
    assert "--force-amm" in _strip_ansi(result.output)


def test_sell_with_force_amm_flag_help():
    result = runner.invoke(app, ["sell", "--help"])
    assert "--force-amm" in _strip_ansi(result.output)


def test_buy_graduated_fallback_json(tmp_path, monkeypatch):
    """Buy auto-falls back to PumpSwap when bonding curve says graduated."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    # Create a wallet
    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with (
        patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy,
        patch("pumpfun_cli.commands.trade.buy_pumpswap", new_callable=AsyncMock) as mock_pumpswap,
    ):
        mock_buy.return_value = {"error": "graduated", "message": "Token has graduated."}
        mock_pumpswap.return_value = {
            "action": "buy",
            "venue": "pumpswap",
            "mint": _FAKE_MINT,
            "sol_spent": 0.01,
            "tokens_received": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "buy",
                _FAKE_MINT,
                "0.01",
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["venue"] == "pumpswap"


def test_sell_error_json(tmp_path, monkeypatch):
    """Sell with error returns proper exit code."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell:
        mock_sell.return_value = {"error": "no_tokens", "message": "No tokens to sell."}

        result = runner.invoke(
            app,
            [
                "--rpc",
                "http://rpc",
                "sell",
                _FAKE_MINT,
                "all",
            ],
        )

    assert result.exit_code == 3


def test_claim_cashback_success_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch(
        "pumpfun_cli.commands.trade.claim_cashback_core", new_callable=AsyncMock
    ) as mock_cb:
        mock_cb.return_value = {
            "action": "claim_cashback",
            "signature": "cbsig",
            "explorer": "https://solscan.io/tx/cbsig",
        }
        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "claim-cashback",
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["action"] == "claim_cashback"


def test_migrate_success_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.migrate_token", new_callable=AsyncMock) as mock_mig:
        mock_mig.return_value = {
            "action": "migrate",
            "mint": _FAKE_MINT,
            "signature": "migsig",
            "explorer": "https://solscan.io/tx/migsig",
        }
        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "migrate",
                _FAKE_MINT,
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["action"] == "migrate"


def test_sell_graduated_fallback_json(tmp_path, monkeypatch):
    """Sell auto-falls back to PumpSwap when bonding curve says graduated."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with (
        patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell,
        patch("pumpfun_cli.commands.trade.sell_pumpswap", new_callable=AsyncMock) as mock_pumpswap,
    ):
        mock_sell.return_value = {"error": "graduated", "message": "Token has graduated."}
        mock_pumpswap.return_value = {
            "action": "sell",
            "venue": "pumpswap",
            "mint": _FAKE_MINT,
            "sol_received": 0.01,
            "tokens_sold": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "sell",
                _FAKE_MINT,
                "all",
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["venue"] == "pumpswap"


def test_buy_invalid_mint_format():
    """Buy with invalid base58 mint exits with error."""
    result = runner.invoke(app, ["--rpc", "https://fake.rpc", "buy", "not-valid-base58!", "0.001"])
    assert result.exit_code != 0
    assert "Invalid mint address" in result.output


def test_sell_invalid_mint_format():
    """Sell with invalid base58 mint exits with error."""
    result = runner.invoke(app, ["--rpc", "https://fake.rpc", "sell", "not-valid-base58!", "all"])
    assert result.exit_code != 0
    assert "Invalid mint address" in result.output


def test_buy_priority_fee_flag_forwarded(tmp_path, monkeypatch):
    """--priority-fee and --compute-units flags are forwarded to buy_token."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy:
        mock_buy.return_value = {
            "action": "buy",
            "mint": _FAKE_MINT,
            "sol_spent": 0.01,
            "tokens_received": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "--priority-fee",
                "50000",
                "--compute-units",
                "200000",
                "buy",
                _FAKE_MINT,
                "0.01",
            ],
        )

    assert result.exit_code == 0
    call_kwargs = mock_buy.call_args
    assert call_kwargs.kwargs.get("priority_fee") == 50000
    assert call_kwargs.kwargs.get("compute_units") == 200000


def test_buy_dry_run_flag(tmp_path, monkeypatch):
    """--dry-run flag produces simulation output with dry_run: true."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy:
        mock_buy.return_value = {
            "dry_run": True,
            "action": "buy",
            "venue": "bonding_curve",
            "mint": _FAKE_MINT,
            "sol_in": 0.01,
            "expected_tokens": 1234.56,
            "effective_price_sol": 0.0000081,
            "spot_price_sol": 0.000008,
            "price_impact_pct": 1.25,
            "min_tokens_out": 1049.87,
            "slippage_pct": 15,
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "buy", "--dry-run", _FAKE_MINT, "0.01"],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["action"] == "buy"
    assert "signature" not in data
    call_kwargs = mock_buy.call_args
    assert call_kwargs.kwargs.get("dry_run") is True


def test_sell_dry_run_flag(tmp_path, monkeypatch):
    """--dry-run flag on sell produces simulation output."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell:
        mock_sell.return_value = {
            "dry_run": True,
            "action": "sell",
            "venue": "bonding_curve",
            "mint": _FAKE_MINT,
            "tokens_in": 1000.0,
            "expected_sol": 0.082,
            "effective_price_sol": 0.000082,
            "spot_price_sol": 0.000083,
            "price_impact_pct": -1.2,
            "min_sol_out": 0.0697,
            "slippage_pct": 15,
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "sell", "--dry-run", _FAKE_MINT, "1000"],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["action"] == "sell"


def test_buy_insufficient_balance_json(tmp_path, monkeypatch):
    """CLI-level test: core returns insufficient_balance error, verify exit code 1 and message."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy:
        mock_buy.return_value = {
            "error": "insufficient_balance",
            "message": "Insufficient SOL balance.",
            "available_sol": 0.000001,
            "required_sol": 0.01293,
        }

        result = runner.invoke(
            app,
            ["--rpc", "http://rpc", "buy", _FAKE_MINT, "0.01"],
        )

    assert result.exit_code == 1
    assert "Insufficient" in result.output


def test_sell_insufficient_balance_json(tmp_path, monkeypatch):
    """CLI-level test: core returns insufficient_balance error for sell."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell:
        mock_sell.return_value = {
            "error": "insufficient_balance",
            "message": "Insufficient token balance.",
            "available_tokens": 0.5,
            "required_tokens": 1000.0,
        }

        result = runner.invoke(
            app,
            ["--rpc", "http://rpc", "sell", _FAKE_MINT, "1000"],
        )

    assert result.exit_code == 1
    assert "Insufficient" in result.output


def test_buy_slippage_negative():
    """Buy with negative slippage exits with error."""
    result = runner.invoke(
        app, ["--rpc", "https://fake.rpc", "buy", "--slippage", "-5", _FAKE_MINT, "0.01"]
    )
    assert result.exit_code != 0
    assert "Slippage must be between 0 and 100" in result.output


def test_buy_slippage_above_100():
    """Buy with slippage above 100 exits with error."""
    result = runner.invoke(
        app, ["--rpc", "https://fake.rpc", "buy", "--slippage", "999", _FAKE_MINT, "0.01"]
    )
    assert result.exit_code != 0
    assert "Slippage must be between 0 and 100" in result.output


def test_sell_slippage_negative():
    """Sell with negative slippage exits with error."""
    result = runner.invoke(
        app, ["--rpc", "https://fake.rpc", "sell", "--slippage", "-5", _FAKE_MINT, "all"]
    )
    assert result.exit_code != 0
    assert "Slippage must be between 0 and 100" in result.output


def test_sell_slippage_above_100():
    """Sell with slippage above 100 exits with error."""
    result = runner.invoke(
        app, ["--rpc", "https://fake.rpc", "sell", "--slippage", "999", _FAKE_MINT, "all"]
    )
    assert result.exit_code != 0
    assert "Slippage must be between 0 and 100" in result.output


def test_buy_slippage_zero(tmp_path, monkeypatch):
    """Buy with slippage=0 is valid (boundary)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy:
        mock_buy.return_value = {
            "action": "buy",
            "mint": _FAKE_MINT,
            "sol_spent": 0.01,
            "tokens_received": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "buy", "--slippage", "0", _FAKE_MINT, "0.01"],
        )

    assert result.exit_code == 0
    assert "Slippage must be between" not in result.output


def test_buy_slippage_100(tmp_path, monkeypatch):
    """Buy with slippage=100 is valid (boundary)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy:
        mock_buy.return_value = {
            "action": "buy",
            "mint": _FAKE_MINT,
            "sol_spent": 0.01,
            "tokens_received": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "buy", "--slippage", "100", _FAKE_MINT, "0.01"],
        )

    assert result.exit_code == 0
    assert "Slippage must be between" not in result.output


def test_sell_slippage_zero(tmp_path, monkeypatch):
    """Sell with slippage=0 is valid (boundary)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell:
        mock_sell.return_value = {
            "action": "sell",
            "mint": _FAKE_MINT,
            "sol_received": 0.01,
            "tokens_sold": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "sell", "--slippage", "0", _FAKE_MINT, "all"],
        )

    assert result.exit_code == 0
    assert "Slippage must be between" not in result.output


def test_sell_slippage_100(tmp_path, monkeypatch):
    """Sell with slippage=100 is valid (boundary)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as mock_sell:
        mock_sell.return_value = {
            "action": "sell",
            "mint": _FAKE_MINT,
            "sol_received": 0.01,
            "tokens_sold": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            ["--json", "--rpc", "http://rpc", "sell", "--slippage", "100", _FAKE_MINT, "all"],
        )

    assert result.exit_code == 0
    assert "Slippage must be between" not in result.output


def test_buy_json_output_has_expected_keys(tmp_path, monkeypatch):
    """Verify JSON buy output has all expected keys."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")

    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")

    with (
        patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as mock_buy,
        patch("pumpfun_cli.commands.trade.buy_pumpswap", new_callable=AsyncMock) as mock_pumpswap,
    ):
        mock_buy.return_value = {"error": "graduated", "message": "Token has graduated."}
        mock_pumpswap.return_value = {
            "action": "buy",
            "venue": "pumpswap",
            "mint": _FAKE_MINT,
            "sol_spent": 0.01,
            "tokens_received": 100.0,
            "signature": "sig",
            "explorer": "https://solscan.io/tx/sig",
        }

        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                "http://rpc",
                "buy",
                _FAKE_MINT,
                "0.01",
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    expected_keys = {
        "action",
        "venue",
        "mint",
        "sol_spent",
        "tokens_received",
        "signature",
        "explorer",
    }
    assert expected_keys.issubset(data.keys())
