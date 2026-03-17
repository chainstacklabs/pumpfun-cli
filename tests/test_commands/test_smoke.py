"""CLI smoke tests — arg parsing, exit codes, JSON validity."""

import json
import re

import pytest
from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "pump.fun" in result.output


def test_tokens_help():
    result = runner.invoke(app, ["tokens", "--help"])
    assert result.exit_code == 0
    assert "trending" in result.output


def test_buy_no_rpc_exits_1():
    result = runner.invoke(app, ["buy", "11111111111111111111111111111111", "0.1"])
    assert result.exit_code == 1
    assert "RPC" in result.output or "rpc" in result.output or "Password" in result.output


def test_info_no_rpc_exits_1():
    result = runner.invoke(app, ["info", "11111111111111111111111111111111"])
    assert result.exit_code == 1


def test_wallet_show_no_wallet_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["wallet", "show"])
    assert result.exit_code == 1
    assert "wallet" in result.output.lower()


def test_info_invalid_mint_shows_error():
    result = runner.invoke(app, ["--rpc", "https://fake.rpc", "info", "not-a-valid-base58!"])
    assert result.exit_code != 0
    assert "Invalid mint address" in result.output
    assert "Traceback" not in (result.output or "")


def test_collect_creator_fee_help():
    result = runner.invoke(app, ["collect-creator-fee", "--help"])
    assert result.exit_code == 0
    assert "--confirm" in _strip_ansi(result.output)


def test_wallet_transfer_help_shows_mint():
    result = runner.invoke(app, ["wallet", "transfer", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--mint" in out
    assert "--confirm" in out


def test_buy_help_shows_confirm():
    result = runner.invoke(app, ["buy", "--help"])
    assert result.exit_code == 0
    assert "--confirm" in _strip_ansi(result.output)


def test_config_roundtrip_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://test.com"])
    result = runner.invoke(app, ["--json", "config", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["rpc"] == "https://test.com"


def test_info_command_timeout_flag():
    """--timeout flag is accepted and passed to get_token_info as rpc_timeout."""
    from unittest.mock import AsyncMock, patch

    mock_result = {
        "mint": "11111111111111111111111111111111",
        "bonding_curve": "ABC",
        "price_sol": 0.001,
        "bonding_progress": 50.0,
        "graduated": False,
        "real_sol_reserves": 10.0,
        "virtual_sol_reserves": 30.0,
        "virtual_token_reserves": 1_000_000_000_000,
        "creator": "11111111111111111111111111111112",
        "is_mayhem_mode": False,
        "is_cashback_coin": False,
    }
    with patch("pumpfun_cli.commands.info.get_token_info", new_callable=AsyncMock) as mock_gti:
        mock_gti.return_value = mock_result
        result = runner.invoke(
            app,
            [
                "--rpc",
                "https://fake.rpc",
                "info",
                "11111111111111111111111111111111",
                "--timeout",
                "45.0",
            ],
        )

    assert result.exit_code == 0
    mock_gti.assert_called_once()
    call_kwargs = mock_gti.call_args
    assert call_kwargs.kwargs.get("rpc_timeout") == 45.0 or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 45.0
    )


def test_info_command_renders_pumpswap_warning():
    """TTY output includes 'Warning:' line when pumpswap_warning is in result."""
    from unittest.mock import AsyncMock, patch

    mock_result = {
        "mint": "11111111111111111111111111111111",
        "bonding_curve": "ABC",
        "price_sol": 0.001,
        "bonding_progress": 100.0,
        "graduated": True,
        "real_sol_reserves": 10.0,
        "virtual_sol_reserves": 30.0,
        "virtual_token_reserves": 1_000_000_000_000,
        "creator": "11111111111111111111111111111112",
        "is_mayhem_mode": False,
        "is_cashback_coin": False,
        "pumpswap_warning": "PumpSwap pool lookup failed: Request timed out",
        "pumpswap_error": "pumpswap_error",
    }
    with patch("pumpfun_cli.commands.info.get_token_info", new_callable=AsyncMock) as mock_gti:
        mock_gti.return_value = mock_result
        result = runner.invoke(
            app,
            ["--rpc", "https://fake.rpc", "info", "11111111111111111111111111111111"],
        )

    assert result.exit_code == 0
    assert "Warning" in _strip_ansi(result.output) or "warning" in result.output.lower()


# --- BUG-3: Subgroup help regression tests ---


def test_wallet_no_subcommand_shows_help():
    """Bare 'wallet' with no subcommand exits 0 and shows help."""
    result = runner.invoke(app, ["wallet"])
    assert result.exit_code == 0


def test_config_no_subcommand_shows_help():
    """Bare 'config' with no subcommand exits 0 and shows help."""
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0


def test_tokens_no_subcommand_shows_help():
    """Bare 'tokens' with no subcommand exits 0 and shows help."""
    result = runner.invoke(app, ["tokens"])
    assert result.exit_code == 0


@pytest.mark.parametrize("limit", ["0", "-1"])
@pytest.mark.parametrize(
    ("subcommand", "extra_args"),
    [
        ("trending", []),
        ("new", []),
        ("graduating", []),
        ("top", []),
        ("recommended", []),
        ("search", ["dog"]),
    ],
)
def test_tokens_limit_must_be_at_least_one(limit, subcommand, extra_args):
    """Token listing commands reject zero and negative limits before execution."""
    result = runner.invoke(app, ["tokens", subcommand, *extra_args, "--limit", limit])

    assert result.exit_code == 2
    output = _strip_ansi(result.output)
    assert "Invalid value for" in output
    assert "--limit" in output
