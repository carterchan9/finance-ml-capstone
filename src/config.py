"""Configuration loader for Stage 1.

Loads and parses config/stage1.toml into a typed dictionary.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_stage1_config(config_path: str = "config/stage1.toml") -> dict[str, Any]:
    """Load Stage 1 configuration from TOML file.

    Args:
        config_path: Path to the TOML config file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        tomllib.TOMLDecodeError: If config file is invalid TOML.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("rb") as f:
        return tomllib.load(f)


if __name__ == "__main__":
    # Quick test: python -m src.config
    cfg = load_stage1_config()
    print("Config loaded successfully")
    print(f"Universe size: {len(cfg['data']['universe'])}")
    print(f"Date range: {cfg['data']['start_date']} to {cfg['data']['end_date']}")
    print(f"DB path: {cfg['paths']['db_path']}")