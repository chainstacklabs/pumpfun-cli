from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


def test_launch_empty_name(tmp_path, monkeypatch):
    """launch rejects empty token name."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "", "--ticker", "TST", "--desc", "test"])
    assert result.exit_code != 0
    assert "name" in result.output.lower()


def test_launch_whitespace_name(tmp_path, monkeypatch):
    """launch rejects whitespace-only token name."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "   ", "--ticker", "TST", "--desc", "test"])
    assert result.exit_code != 0
    assert "name" in result.output.lower()


def test_launch_empty_ticker(tmp_path, monkeypatch):
    """launch rejects empty ticker."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "MyToken", "--ticker", "", "--desc", "test"])
    assert result.exit_code != 0
    assert "ticker" in result.output.lower()


def test_launch_whitespace_ticker(tmp_path, monkeypatch):
    """launch rejects whitespace-only ticker."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "MyToken", "--ticker", "   ", "--desc", "test"])
    assert result.exit_code != 0
    assert "ticker" in result.output.lower()


def test_launch_empty_desc(tmp_path, monkeypatch):
    """launch rejects empty description."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "MyToken", "--ticker", "TST", "--desc", ""])
    assert result.exit_code != 0
    assert "description" in result.output.lower()


def test_launch_whitespace_desc(tmp_path, monkeypatch):
    """launch rejects whitespace-only description."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", "MyToken", "--ticker", "TST", "--desc", "   "])
    assert result.exit_code != 0
    assert "description" in result.output.lower()