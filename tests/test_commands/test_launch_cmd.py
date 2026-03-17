import pytest
from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


@pytest.mark.parametrize("name,ticker,desc,expected_error", [
    ("", "TST", "test", "name"),
    ("   ", "TST", "test", "name"),
    ("MyToken", "", "test", "ticker"),
    ("MyToken", "   ", "test", "ticker"),
    ("MyToken", "TST", "", "description"),
    ("MyToken", "TST", "   ", "description"),
])
def test_launch_rejects_empty_inputs(tmp_path, monkeypatch, name, ticker, desc, expected_error):
    """launch rejects empty or whitespace-only name, ticker, or description."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["launch", "--name", name, "--ticker", ticker, "--desc", desc])
    assert result.exit_code != 0
    assert expected_error in result.output.lower()