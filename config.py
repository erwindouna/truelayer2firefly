"""Class to handle the configuration for Plaid2Firefly"""
import json
from pathlib import Path
from typing import Any

import logging

_LOGGER = logging.getLogger(__name__)

class Config:
    """Configuration class for Plaid2Firefly"""

    def __init__(self, path: str = "config.json")-> None:
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("{}")
        self._load()

    def _load(self) -> None:
        """Load the configuration from the JSON file"""
        with open(self.path, "r") as f:
            self._config = json.load(f)

    def get(self, key: str, default=None) -> Any:
        """Get a configuration value, always using the latest available"""
        self._load() 
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        self._config[key] = value
        _LOGGER.info(f"Saving configuration: {key} to {value}")
        self._save()

    def update(self, new_values: dict) -> None:
        """Update multiple configuration values"""
        self._config.update(new_values)
        self._save()

    def delete(self, key: str)-> None:
        """Delete a configuration value"""
        if key in self._config:
            del self._config[key]
            _LOGGER.info(f"Deleting configuration: {key}")
            self._save()
        else:
            _LOGGER.warning(f"Key {key} not found in configuration")

    def _save(self) -> None:
        """Save the current configuration to the JSON file"""
        with open(self.path, "w") as f:
            json.dump(self._config, f, indent=4)