from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


@pytest.mark.parametrize(("name", "ticker", "desc", "expected_error"), [
    ("", "TST", "test", "token name cannot be empty."),
    ("   ", "TST", "test", "token name cannot be empty."),
    ("MyToken", "", "test", "token ticker cannot be empty."),
    ("MyToken", "   ", "test", "token ticker cannot be empty."),
    ("MyToken", "TST", "", "token description cannot be empty."),
    ("MyToken", "TST", "   ", "token description cannot be empty."),
])
def test_launch_rejects_empty_inputs(tmp_path, monkeypatch, name, ticker, desc, expected_error):
    """launch rejects empty or whitespace-only name, ticker, or description."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    launch_token_mock = Mock(side_effect=AssertionError("launch_token must not be called for invalid input"))
    monkeypatch.setattr("pumpfun_cli.commands.launch.launch_token", launch_token_mock)

    result = runner.invoke(app, ["launch", "--name", name, "--ticker", ticker, "--desc", desc])
    assert result.exit_code != 0
    assert expected_error in result.output.lower()
    launch_token_mock.assert_not_called()