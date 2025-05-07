"""Class to handle the configuration for Plaid2Firefly"""
import json
from pathlib import Path
from typing import Any


class Config:
    """Configuration class for Plaid2Firefly"""

    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("{}")
        self._load()

    def _load(self):
        """Load the configuration from the JSON file"""
        with open(self.path, "r") as f:
            self._config = json.load(f)

    def get(self, key: str, default=None):
        """Get a configuration value, always using the latest available"""
        self._load() 
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value"""
        self._config[key] = value
        self._save()

    def update(self, new_values: dict):
        """Update multiple configuration values"""
        self._config.update(new_values)
        self._save()

    def _save(self):
        """Save the current configuration to the JSON file"""
        with open(self.path, "w") as f:
            json.dump(self._config, f, indent=4)