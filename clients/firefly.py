"""Class to handle TrueLayer API calls."""

from datetime import datetime
import logging
import os
import re
import time
from typing import Any, Self
import humanize
import json

import httpx
from pytest import param
from yarl import URL
import jwt
from config import Config

from exceptions import (
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyError,
    TrueLayer2FireflyTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class FireflyClient:
    """Firefly client for making API calls"""

    def __init__(
        self,
        request_timeout: float = 10.0,
        access_token: str | None = None,
        url: str | None = None,
    ):
        """Initialize the Firefly client"""
        self.url: str | None = url
        self.request_timeout: float = request_timeout
        self.access_token: str | None = access_token

        self._config: Config = Config()
        self._request_timeout: float = request_timeout
        self._client: httpx.AsyncClient | None = None

    async def _request(
        self,
        uri: str,
        *,
        auth: bool = False,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make a request to the Firefly API"""
        self.access_token = self._config.get("firefly_access_token")
        self.url = self._config.get("firefly_api_url")

        # No refresh mechanism is needed, since the token is valid for 55 years

        if auth:
            url = str(URL(self.url).join(URL(uri)))
        else:
            url = str(URL(self.url).join(URL(f"api/v1/{uri}")))

        headers = {
            "Accept": "application/json",
            "User-Agent": "TrueLayer2Firefly",
        }

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._request_timeout)

        if params:
            params = {k: v for k, v in params.items() if v is not None}
        if json:
            json = {k: v for k, v in json.items() if v is not None}

        try:
            if method == "POST":
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=params,
                )
            else:
                if self._config.get("firefly_access_token"):
                    headers["Authorization"] = (
                        f"Bearer {self._config.get('firefly_access_token')}"
                    )

                _LOGGER.debug("URL: %s", url)
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params if method == "GET" else None,
                    json=json if method == "POST" and not auth else None,
                )
            response.raise_for_status()
        except httpx.RequestError as err:
            msg = f"Request error during {method} {url}: {err}"
            raise TrueLayer2FireflyConnectionError(msg) from err
        except httpx.HTTPStatusError as err:
            msg = f"HTTP status error during {method} {url}: {err.response.status_code}, {err.response.text}"
            raise TrueLayer2FireflyConnectionError(msg) from err

        content_type = response.headers.get("Content-Type", "")
        if "application/vnd.api+json" not in content_type:
            msg = "Unexpected content type response from the Firefly API"
            raise TrueLayer2FireflyError(
                msg,
                {"Content-Type": content_type, "response": response.text},
            )

        return response

    async def healthcheck(self) -> None:
        """Check the health of the Firefly API."""
        return await self._request(
            uri="about",
            method="GET",
        )

    async def get_accounts(self) -> dict[str, Any]:
        """Get the accounts from the Firefly API."""
        return await self._request(
            uri="accounts",
            method="GET",
        )

    async def close(self) -> None:
        """Close the HTTPX client session."""
        if self._client:
            await self._client.aclose()
            _LOGGER.info("Closed HTTPX client session")

    async def __aenter__(self) -> Self:
        """Async enter."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._request_timeout)
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Async exit."""
        await self.close()
