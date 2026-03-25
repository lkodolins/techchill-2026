"""Simple JSON config store at ~/.forgechannels/config.json."""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".forgechannels"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load config from disk. Returns empty dict if no config exists."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    """Save config to disk."""
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_config_value(key: str, default=None):
    """Get a single config value."""
    return load_config().get(key, default)


def set_config_value(key: str, value) -> None:
    """Set a single config value."""
    config = load_config()
    config[key] = value
    save_config(config)
