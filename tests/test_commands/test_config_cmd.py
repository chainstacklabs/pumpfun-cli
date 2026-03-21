import json

from typer.testing import CliRunner

from pumpfun_cli.cli import app

runner = CliRunner()


def test_config_set_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["config", "get", "rpc"])
    assert result.exit_code == 0
    assert "https://example.com" in result.output


def test_config_list(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert "rpc" in result.output


def test_config_list_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["--json", "config", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["rpc"] == "https://example.com"


def test_config_set_json_output(tmp_path, monkeypatch):
    """config set outputs JSON with --json flag (leading)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["--json", "config", "set", "rpc", "https://example.com"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"key": "rpc", "value": "https://example.com", "status": "saved"}


def test_config_set_json_trailing(tmp_path, monkeypatch):
    """config set outputs JSON with --json flag (trailing)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["config", "set", "rpc", "https://example.com", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"key": "rpc", "value": "https://example.com", "status": "saved"}


def test_config_get_json_output(tmp_path, monkeypatch):
    """config get outputs JSON with --json flag."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["--json", "config", "get", "rpc"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"key": "rpc", "value": "https://example.com"}


def test_config_delete_json_output(tmp_path, monkeypatch):
    """config delete outputs JSON with --json flag."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["--json", "config", "delete", "rpc"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"key": "rpc", "status": "deleted"}


def test_config_get_json_trailing(tmp_path, monkeypatch):
    """config get outputs JSON with --json flag (trailing)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner.invoke(app, ["config", "set", "rpc", "https://example.com"])
    result = runner.invoke(app, ["config", "get", "rpc", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"key": "rpc", "value": "https://example.com"}


def test_config_set_unknown_key(tmp_path, monkeypatch):
    """config set rejects unknown config keys and does not persist them."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["config", "set", "rpcc", "https://example.com"])
    assert result.exit_code != 0
    assert "unknown config key" in result.output.lower()
    assert "valid keys" in result.output.lower()

    # Assert the invalid key was not persisted
    list_result = runner.invoke(app, ["--json", "config", "list"])
    assert list_result.exit_code == 0
    import json
    data = json.loads(list_result.output) if list_result.output.strip() else {}
    assert "rpcc" not in data