from pumpfun_cli.core.config import (
    get_config_dir,
    load_config,
    resolve_value,
    save_config_value,
)


def test_config_dir_default():
    path = get_config_dir()
    assert path.name == "pumpfun-cli"


def test_save_and_load_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config_value("rpc", "https://example.com")
    cfg = load_config()
    assert cfg["rpc"] == "https://example.com"


def test_config_flag_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PUMPFUN_RPC", "from-env")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config_value("rpc", "from-file")
    assert resolve_value("rpc", flag="from-flag") == "from-flag"
    assert resolve_value("rpc", flag=None) == "from-env"


def test_resolve_value_zero_flag_not_ignored(tmp_path, monkeypatch):
    """Flag value '0' should not be treated as falsy."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_RPC", "from-env")
    assert resolve_value("rpc", flag="0") == "0"


def test_resolve_value_zero_env_not_ignored(tmp_path, monkeypatch):
    """Env value '0' should not be treated as falsy."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PRIORITY_FEE", "0")
    assert resolve_value("priority_fee") == "0"


def test_resolve_priority_fee_from_env(monkeypatch):
    monkeypatch.setenv("PUMPFUN_PRIORITY_FEE", "50000")
    assert resolve_value("priority_fee") == "50000"


def test_resolve_compute_units_from_env(monkeypatch):
    monkeypatch.setenv("PUMPFUN_COMPUTE_UNITS", "300000")
    assert resolve_value("compute_units") == "300000"


def test_resolve_priority_fee_flag_overrides_env(monkeypatch):
    monkeypatch.setenv("PUMPFUN_PRIORITY_FEE", "50000")
    assert resolve_value("priority_fee", flag="100000") == "100000"
