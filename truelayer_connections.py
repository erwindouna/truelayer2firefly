"""Helpers for persisting multiple TrueLayer connections in config."""

from __future__ import annotations

from typing import Any

from config import Config


def _connection_key(connection: dict[str, Any]) -> str:
    """Return a stable key used to de-duplicate persisted connections."""
    credentials_id = connection.get("credentials_id")
    if credentials_id:
        return f"credentials:{credentials_id}"

    access_token = connection.get("access_token")
    if access_token:
        return f"token:{access_token}"

    return "unknown"


def get_truelayer_connections(config: Config) -> list[dict[str, Any]]:
    """Load configured TrueLayer connections, including legacy single-token format."""
    raw_connections = config.get("truelayer_connections", [])
    connections: list[dict[str, Any]] = []

    if isinstance(raw_connections, list):
        for item in raw_connections:
            if not isinstance(item, dict):
                continue
            access_token = item.get("access_token")
            refresh_token = item.get("refresh_token")
            if not access_token or not refresh_token:
                continue
            connections.append(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "credentials_id": item.get("credentials_id"),
                    "expiration_date": item.get("expiration_date"),
                }
            )

    # Backward compatibility with older config that stored only one token pair.
    if not connections:
        access_token = config.get("truelayer_access_token")
        refresh_token = config.get("truelayer_refresh_token")
        if access_token and refresh_token:
            connections.append(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "credentials_id": config.get("truelayer_credentials_id"),
                    "expiration_date": config.get("truelayer_expiration_date"),
                }
            )

    deduplicated: dict[str, dict[str, Any]] = {}
    for connection in connections:
        deduplicated[_connection_key(connection)] = connection

    return list(deduplicated.values())


def activate_truelayer_connection(config: Config, connection: dict[str, Any]) -> None:
    """Make a persisted connection the active one used by the TrueLayer client."""
    config.set("truelayer_access_token", connection.get("access_token"))
    config.set("truelayer_refresh_token", connection.get("refresh_token"))

    credentials_id = connection.get("credentials_id")
    if credentials_id:
        config.set("truelayer_credentials_id", credentials_id)

    expiration_date = connection.get("expiration_date")
    if expiration_date:
        config.set("truelayer_expiration_date", expiration_date)


def upsert_active_truelayer_connection(config: Config) -> list[dict[str, Any]]:
    """Store active token set in the multi-connection list and return updated list."""
    access_token = config.get("truelayer_access_token")
    refresh_token = config.get("truelayer_refresh_token")
    if not access_token or not refresh_token:
        return get_truelayer_connections(config)

    updated_connection = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "credentials_id": config.get("truelayer_credentials_id"),
        "expiration_date": config.get("truelayer_expiration_date"),
    }

    current = get_truelayer_connections(config)
    deduplicated: dict[str, dict[str, Any]] = {
        _connection_key(item): item for item in current
    }
    deduplicated[_connection_key(updated_connection)] = updated_connection

    connection_list = list(deduplicated.values())
    config.set("truelayer_connections", connection_list)
    return connection_list
