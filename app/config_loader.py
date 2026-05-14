"""Loads and caches YAML configuration files."""
import yaml
from pathlib import Path
from typing import List, Dict, Any

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> Any:
    path = _CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources() -> List[Dict[str, Any]]:
    data = _load_yaml("sources.yml")
    return data.get("sources", [])


def load_ev_positive_keywords() -> Dict[str, Any]:
    return _load_yaml("ev_positive_keywords.yml")


def load_ev_negative_keywords() -> Dict[str, Any]:
    return _load_yaml("ev_negative_keywords.yml")
