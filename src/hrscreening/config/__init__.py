"\"\"\"Configuration management utilities.\"\"\""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigManager:
    """Simple YAML-backed configuration loader."""

    def __init__(self, base_path: str | Path):
        self._base_path = Path(base_path)

    def load(self, name: str) -> dict[str, Any]:
        """Load a YAML configuration by name without file extension."""
        path = self._base_path / f"{name}.yaml"
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)


__all__ = ["ConfigManager"]

