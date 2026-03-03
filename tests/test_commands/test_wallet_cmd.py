"""Tests for commands/wallet.py — address validation at command layer."""

import os
from unittest.mock import patch

from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


class _FakeState:
    rpc = "http://fake-rpc"
    json_mode = False
    keyfile = None
    priority_fee = None
    compute_units = None


def _make_wallet(tmp_path):
    """Create a test wallet and return its path."""
    from solders.keypair import Keypair

    from pumpfun_cli.crypto import encrypt_keypair

    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(Keypair(), "testpass", keyfile)
    return str(keyfile)


def test_wallet_transfer_invalid_recipient(tmp_path):
    """Invalid recipient address exits with error."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    with patch.dict(os.environ, env):
        result = runner.invoke(
            app,
            ["--keyfile", keyfile, "wallet", "transfer", "invalidrecipient", "1.0"],
        )
    assert result.exit_code != 0


def test_wallet_transfer_invalid_mint_option(tmp_path):
    """Invalid --mint option exits with error."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    with patch.dict(os.environ, env):
        result = runner.invoke(
            app,
            [
                "--keyfile",
                keyfile,
                "wallet",
                "transfer",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "1.0",
                "--mint",
                "invalidmint",
            ],
        )
    assert result.exit_code != 0


# --- BUG-5/6/7: wallet create overwrite & password tests ---


def test_wallet_create_refuses_overwrite_shows_address(tmp_path):
    """Existing wallet + no --force → exit non-zero, output has pubkey and --force hint."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "create"])
    assert result.exit_code != 0
    assert "--force" in _strip_ansi(result.output)


def test_wallet_create_force_overwrites(tmp_path):
    """Existing wallet + --force → exit 0."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "create", "--force"])
    assert result.exit_code == 0


def test_wallet_create_env_password_skips_confirm(tmp_path):
    """PUMPFUN_PASSWORD set → succeeds without stdin (no confirmation prompt)."""
    keyfile = str(tmp_path / "wallet.enc")
    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "create"])
    assert result.exit_code == 0


def test_wallet_create_flag_password_skips_confirm(tmp_path):
    """--password flag → succeeds without stdin."""
    keyfile = str(tmp_path / "wallet.enc")
    result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "create", "--password", "mypass"])
    assert result.exit_code == 0


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for assertion matching."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_wallet_create_help_shows_password_options():
    """Help text mentions --password and PUMPFUN_PASSWORD."""
    result = runner.invoke(app, ["wallet", "create", "--help"])
    plain = _strip_ansi(result.output)
    assert "--password" in plain
    assert "PUMPFUN_PASSWORD" in plain


def test_wallet_import_refuses_overwrite_shows_address(tmp_path):
    """Existing wallet + no --force → exit non-zero with address."""
    keyfile = _make_wallet(tmp_path)
    # Create a keypair JSON to import
    import json

    from solders.keypair import Keypair

    kp = Keypair()
    kp_path = tmp_path / "keypair.json"
    kp_path.write_text(json.dumps(list(bytes(kp))))

    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "import", str(kp_path)])
    assert result.exit_code != 0
    assert "--force" in _strip_ansi(result.output)


def test_wallet_import_force_overwrites(tmp_path):
    """Existing wallet + --force → exit 0."""
    keyfile = _make_wallet(tmp_path)
    import json

    from solders.keypair import Keypair

    kp = Keypair()
    kp_path = tmp_path / "keypair.json"
    kp_path.write_text(json.dumps(list(bytes(kp))))

    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(
            app, ["--keyfile", keyfile, "wallet", "import", str(kp_path), "--force"]
        )
    assert result.exit_code == 0


def test_wallet_import_env_password_skips_confirm(tmp_path):
    """PUMPFUN_PASSWORD set → import succeeds without stdin."""
    import json

    from solders.keypair import Keypair

    keyfile = str(tmp_path / "wallet.enc")
    kp = Keypair()
    kp_path = tmp_path / "keypair.json"
    kp_path.write_text(json.dumps(list(bytes(kp))))

    env = {"PUMPFUN_PASSWORD": "testpass"}
    with patch.dict(os.environ, env):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "import", str(kp_path)])
    assert result.exit_code == 0


# --- BUG-13: transfer all SOL command tests ---


def test_wallet_transfer_all_sol_accepted(tmp_path):
    """CLI accepts 'all' without --mint, patches core to return success."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {
        "action": "transfer",
        "from": "SomeFrom",
        "to": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "sol_amount": 0.99,
        "signature": "fakesig",
        "explorer": "https://solscan.io/tx/fakesig",
    }
    with (
        patch.dict(os.environ, env),
        patch("pumpfun_cli.commands.wallet.transfer_all_sol", return_value=mock_result) as mock_fn,
    ):
        result = runner.invoke(
            app,
            [
                "--keyfile",
                keyfile,
                "wallet",
                "transfer",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "all",
            ],
        )
    assert result.exit_code == 0
    mock_fn.assert_called_once()


def test_wallet_transfer_all_sol_error(tmp_path):
    """Core returns error dict → non-zero exit."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {
        "error": "insufficient_balance",
        "message": "Balance too low to cover transaction fees.",
    }
    with (
        patch.dict(os.environ, env),
        patch("pumpfun_cli.commands.wallet.transfer_all_sol", return_value=mock_result),
    ):
        result = runner.invoke(
            app,
            [
                "--keyfile",
                keyfile,
                "wallet",
                "transfer",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "all",
            ],
        )
    assert result.exit_code != 0


# --- BUG-12: --show-empty flag tests ---


def test_wallet_tokens_default_hides_empty(tmp_path):
    """Default wallet tokens passes show_empty=False to core."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {"pubkey": "FakePubkey", "token_accounts": []}
    with (
        patch.dict(os.environ, env),
        patch(
            "pumpfun_cli.commands.wallet.list_token_accounts", return_value=mock_result
        ) as mock_fn,
    ):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "tokens"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()
    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("show_empty") is False or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] is False
    )


def test_wallet_tokens_show_empty_flag(tmp_path):
    """--show-empty passes show_empty=True to core."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {"pubkey": "FakePubkey", "token_accounts": []}
    with (
        patch.dict(os.environ, env),
        patch(
            "pumpfun_cli.commands.wallet.list_token_accounts", return_value=mock_result
        ) as mock_fn,
    ):
        result = runner.invoke(app, ["--keyfile", keyfile, "wallet", "tokens", "--show-empty"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()
    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("show_empty") is True or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] is True
    )


# --- BUG-14: wallet drain command tests ---


def test_wallet_drain_happy_path(tmp_path):
    """Drain command with success result exits 0."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {
        "action": "drain",
        "wallet": "SomeWallet",
        "recipient": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "non_empty_token_accounts": [],
        "atas_closed": 2,
        "ata_rent_recovered_sol": 0.004,
        "ata_signature": "atasig",
        "ata_error": None,
        "sol_transferred": 0.99,
        "sol_signature": "solsig",
        "sol_error": None,
    }
    with (
        patch.dict(os.environ, env),
        patch("pumpfun_cli.commands.wallet.drain_wallet", return_value=mock_result),
    ):
        result = runner.invoke(
            app,
            [
                "--keyfile",
                keyfile,
                "wallet",
                "drain",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            ],
        )
    assert result.exit_code == 0


def test_wallet_drain_invalid_recipient(tmp_path):
    """Drain with error dict exits non-zero."""
    keyfile = _make_wallet(tmp_path)
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    mock_result = {
        "error": "invalid_address",
        "message": "Invalid recipient address: invalidrecipient",
    }
    with (
        patch.dict(os.environ, env),
        patch("pumpfun_cli.commands.wallet.drain_wallet", return_value=mock_result),
    ):
        result = runner.invoke(
            app,
            ["--keyfile", keyfile, "wallet", "drain", "invalidrecipient"],
        )
    assert result.exit_code != 0


def test_wallet_drain_no_wallet(tmp_path):
    """Non-existent keyfile exits non-zero."""
    env = {"PUMPFUN_PASSWORD": "testpass", "PUMPFUN_RPC": "http://fake-rpc"}
    keyfile = str(tmp_path / "nonexistent.enc")
    with patch.dict(os.environ, env):
        result = runner.invoke(
            app,
            [
                "--keyfile",
                keyfile,
                "wallet",
                "drain",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            ],
        )
    assert result.exit_code != 0
