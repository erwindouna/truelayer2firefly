"""Tests for multi-connection TrueLayer config helpers."""

from truelayer_connections import (
    activate_truelayer_connection,
    get_truelayer_connections,
    upsert_active_truelayer_connection,
)


class FakeConfig:
    """Minimal config double with get/set support."""

    def __init__(self, initial=None):
        self._values = initial or {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


def test_get_connections_from_legacy_single_token() -> None:
    """Legacy single token fields are converted to one connection."""
    config = FakeConfig(
        {
            "truelayer_access_token": "access-1",
            "truelayer_refresh_token": "refresh-1",
            "truelayer_credentials_id": "cred-1",
            "truelayer_expiration_date": 123456,
        }
    )

    connections = get_truelayer_connections(config)

    assert len(connections) == 1
    assert connections[0]["access_token"] == "access-1"
    assert connections[0]["refresh_token"] == "refresh-1"
    assert connections[0]["credentials_id"] == "cred-1"


def test_upsert_active_connection_deduplicates_by_credentials_id() -> None:
    """Upserting a connection with same credentials updates existing record."""
    config = FakeConfig(
        {
            "truelayer_connections": [
                {
                    "access_token": "old-access",
                    "refresh_token": "old-refresh",
                    "credentials_id": "cred-1",
                    "expiration_date": 1,
                }
            ],
            "truelayer_access_token": "new-access",
            "truelayer_refresh_token": "new-refresh",
            "truelayer_credentials_id": "cred-1",
            "truelayer_expiration_date": 2,
        }
    )

    connections = upsert_active_truelayer_connection(config)

    assert len(connections) == 1
    assert connections[0]["access_token"] == "new-access"
    assert connections[0]["refresh_token"] == "new-refresh"
    assert connections[0]["expiration_date"] == 2


def test_activate_connection_sets_active_config_fields() -> None:
    """Activating a connection writes active token fields to config."""
    config = FakeConfig()

    activate_truelayer_connection(
        config,
        {
            "access_token": "access-2",
            "refresh_token": "refresh-2",
            "credentials_id": "cred-2",
            "expiration_date": 3,
        },
    )

    assert config.get("truelayer_access_token") == "access-2"
    assert config.get("truelayer_refresh_token") == "refresh-2"
    assert config.get("truelayer_credentials_id") == "cred-2"
    assert config.get("truelayer_expiration_date") == 3
