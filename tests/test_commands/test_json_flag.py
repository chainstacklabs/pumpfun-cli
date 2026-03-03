"""Tests for --json flag at any position in the command line."""

import json

from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


def test_json_trailing_config_list(tmp_path, monkeypatch):
    """config list --json exits 0, output is valid JSON."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["config", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, dict)


def test_json_trailing_wallet_show(tmp_path, monkeypatch):
    """wallet show --json does NOT exit code 2 (Click 'No such option')."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["wallet", "show", "--json"])
    assert result.exit_code != 2


def test_json_trailing_info():
    """info <mint> --json does NOT exit code 2."""
    result = runner.invoke(app, ["info", "11111111111111111111111111111111", "--json"])
    assert result.exit_code != 2


def test_json_leading_still_works(tmp_path, monkeypatch):
    """--json config list still works (regression)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["--json", "config", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, dict)


def test_json_both_positions_idempotent(tmp_path, monkeypatch):
    """--json config list --json works."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["--json", "config", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, dict)


def test_json_trailing_tokens_trending():
    """tokens trending --json does NOT exit code 2."""
    result = runner.invoke(app, ["tokens", "trending", "--json"])
    assert result.exit_code != 2


def test_json_trailing_buy():
    """buy <mint> <amount> --json does NOT exit code 2."""
    result = runner.invoke(app, ["buy", "11111111111111111111111111111111", "0.1", "--json"])
    assert result.exit_code != 2
