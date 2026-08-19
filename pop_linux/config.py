import os
import stat
import sys
import copy
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "pop_linux"
CONFIG_FILE = CONFIG_DIR / "config.toml"
COOKIES_FILE = CONFIG_DIR / "cookies.json"
HISTORY_DB_FILE = CONFIG_DIR / "history.sqlite3"

DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DEFAULT_CONFIG: dict[str, Any] = {
    "default_provider": "openalex",
    "default_limit": 50,
    "polite_email": "pop-linux@syntaxhouse.com",
    "google_scholar_timeout": 30,
    "user_agent": DEFAULT_USER_AGENT,
    "cookies_file": str(COOKIES_FILE),
    "api_keys": {
        "semanticscholar": "",
        "ncbi": ""
    }
}


def ensure_config_dir() -> Path:
    """Ensures ~/.config/pop_linux directory exists with restricted permissions (0700)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, stat.S_IRWXU)
    except OSError:
        pass  # Best-effort hardening; not fatal if the filesystem rejects it.
    return CONFIG_DIR


def load_config() -> dict[str, Any]:
    """Loads configuration from ~/.config/pop_linux/config.toml, creating defaults if missing."""
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as err:
        print(f"[pop-linux] WARNING: could not read config file {CONFIG_FILE}: {err}. Using defaults.", file=sys.stderr)
        return copy.deepcopy(DEFAULT_CONFIG)

    # Merge with default config to ensure missing keys are populated
    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update(data)
    if "api_keys" in data:
        merged["api_keys"] = (
            {**DEFAULT_CONFIG["api_keys"], **data["api_keys"]}
            if isinstance(data["api_keys"], dict)
            else {**DEFAULT_CONFIG["api_keys"]}
        )
    # Normalize known integer keys; fall back to defaults for missing or invalid values.
    for k in _INT_KEYS:
        v = merged.get(k)
        if isinstance(v, bool) or not isinstance(v, int):
            try:
                merged[k] = int(v)
            except (TypeError, ValueError):
                merged[k] = DEFAULT_CONFIG[k]
    return merged


def save_config(config_data: dict[str, Any]) -> None:
    """Saves dictionary to ~/.config/pop_linux/config.toml with restricted 0600 permissions."""
    ensure_config_dir()
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(config_data, f)
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best-effort hardening; not fatal if the filesystem rejects it.


#: Config keys whose values are expected to be integers (coerced from CLI string input)
_INT_KEYS = {"default_limit", "google_scholar_timeout"}


def _coerce_config_value(key: str, value: Any) -> Any:
    """Coerces CLI string values to the correct type for known config keys."""
    if key in _INT_KEYS and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def update_config_value(key: str, value: Any) -> dict[str, Any]:
    """Updates a top-level or nested key (e.g., 'api_keys.ncbi') in config file."""
    value = _coerce_config_value(key.split(".")[-1], value)
    config = load_config()
    if "." in key:
        parts = key.split(".", 1)
        parent = parts[0]
        child = parts[1]
        if parent not in config or not isinstance(config[parent], dict):
            config[parent] = {}
        config[parent][child] = value
    else:
        config[key] = value
    save_config(config)
    return config

