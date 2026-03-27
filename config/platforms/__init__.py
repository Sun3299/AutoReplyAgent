import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent


def get_platform_config(platform_name: str) -> dict:
    """Get platform configuration by platform name."""
    config_file = CONFIG_DIR / f"{platform_name}.json"
    if not config_file.exists():
        config_file = CONFIG_DIR / "other.json"
    
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)
