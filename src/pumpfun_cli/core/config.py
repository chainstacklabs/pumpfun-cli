"""Config management — TOML file + env var + flag resolution."""

import os
import tomllib
from pathlib import Path

import tomli_w


def get_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "pumpfun-cli"


def get_config_path() -> Path:
    return get_config_dir() / "config.toml"


def load_config() -> dict:
    path = get_config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_config_value(key: str, value: str):
    config = load_config()
    config[key] = value
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)


def delete_config_value(key: str):
    config = load_config()
    if key not in config:
        raise KeyError(key)
    del config[key]
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)


ENV_MAP = {
    "rpc": "PUMPFUN_RPC",
    "keyfile": "PUMPFUN_KEYFILE",
    "priority_fee": "PUMPFUN_PRIORITY_FEE",
    "compute_units": "PUMPFUN_COMPUTE_UNITS",
}

KNOWN_KEYS: frozenset[str] = frozenset(ENV_MAP)

def resolve_value(key: str, flag: str | None = None) -> str | None:
    if flag is not None:
        return flag
    env_name = ENV_MAP.get(key)
    if env_name:
        env_val = os.environ.get(env_name)
        if env_val is not None:
            return env_val
    config = load_config()
    return config.get(key)
