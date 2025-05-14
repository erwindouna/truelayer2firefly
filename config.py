"""Class to handle the configuration for Plaid2Firefly"""

import json
from pathlib import Path
from typing import Any

import logging

_LOGGER = logging.getLogger(__name__)


class Config:
    """Configuration class for Plaid2Firefly"""

    def __init__(self) -> None:
        self.path = Path("data/config.json")
        if not self.path.exists():
            _LOGGER.info("Creating configuration file at %s", self.path)
            self.path.write_text("{}", encoding="utf-8")
        self._load()

    def _load(self) -> None:
        """Load the configuration from the JSON file"""
        with open(self.path, "r", encoding="utf-8") as f:
            self._config = json.load(f)

    def get(self, key: str, default=None) -> Any:
        """Get a configuration value, always using the latest available"""
        self._load()
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        self._config[key] = value
        _LOGGER.info("Saving configuration: %s to %s", key, value)
        self._save()

    def update(self, new_values: dict) -> None:
        """Update multiple configuration values"""
        self._config.update(new_values)
        self._save()

    def delete(self, key: str) -> None:
        """Delete a configuration value"""
        if key in self._config:
            del self._config[key]
            _LOGGER.info("Deleting configuration: %s", key)
            self._save()
        else:
            _LOGGER.warning("Key %s not found in configuration", key)

    def reset(self) -> None:
        """Reset the configuration"""
        _LOGGER.info("Resetting configuration")
        self._config = {}
        self._save()

    def _save(self) -> None:
        """Save the current configuration to the JSON file"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=4)
