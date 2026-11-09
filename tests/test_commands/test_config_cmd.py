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


def test_config_set_rejects_unknown_key(tmp_path, monkeypatch):
    """A typo'd key is refused, lists the valid keys, and is not saved."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(app, ["config", "set", "rpcc", "https://example.com"])
    assert result.exit_code == 2
    assert "Unknown config key: rpcc" in result.output
    assert "compute_units, keyfile, priority_fee, rpc" in result.output
    assert not (tmp_path / "pumpfun-cli" / "config.toml").exists()


def test_config_delete_still_removes_unknown_key(tmp_path, monkeypatch):
    """A typo saved by an older version can still be deleted."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('rpcc = "https://example.com"\n')
    result = runner.invoke(app, ["config", "delete", "rpcc"])
    assert result.exit_code == 0
    assert (config_dir / "config.toml").read_text().strip() == ""
