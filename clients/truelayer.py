"""Class to handle TrueLayer API calls."""

import logging
import os
from typing import Any, Self

import httpx
from yarl import URL
from config import Config

from exceptions import TrueLayer2FireflyConnectionError, TrueLayer2FireflyError, TrueLayer2FireflyTimeoutError

_LOGGER = logging.getLogger(__name__)

class TrueLayerClient:
    """TrueLayer client for making API calls"""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, request_timeout: float = 10.0):
        """Initialize the TrueLayer client"""
        self.client_id: str = client_id
        self.client_secret: str = client_secret
        self.redirect_uri: str = redirect_uri
        self.access_token: str | None = None

        self._config = Config()
        self._request_timeout = request_timeout
        self._client: httpx.AsyncClient | None = None

    async def _request(
        self,
        uri: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make a request to the TrueLayer API"""
        url = URL("https://api.truelayer.com").join(uri)

        headers = {
            "Accept": "application/json, text/plain",
            "User-Agent": "TrueLayer2Firefly",
        }

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._request_timeout)

        # Sanitize params and json by removing None values
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        if json:
            json = {k: v for k, v in json.items() if v is not None}

        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                params=params if method == "GET" else None,
                json=json if method == "POST" else None,
            )
            response.raise_for_status()
        except httpx.RequestError as err:
            msg = f"Request error during {method} {url}: {err}"
            raise TrueLayer2FireflyConnectionError(msg) from err
        except httpx.HTTPStatusError as err:
            msg = f"HTTP status error during {method} {url}: {err.response.status_code}, {err.response.text}"
            raise TrueLayer2FireflyConnectionError(msg) from err

        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            msg = "Unexpected content type response from the TrueLayer API"
            raise TrueLayer2FireflyError(
                msg,
                {"Content-Type": content_type, "response": response.text},
            )

        return response.json()

    async def exchange_authrorization_code(self)-> None:
        """Exchange the authorization code for an access token."""
        if not self.client_id or not self.client_secret:
            raise TrueLayer2FireflyError("Client ID and secret are required")

        url = f"https://{self.env}.truelayer.com/connect/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": os.getenv("AUTHORIZATION_CODE"),
            "redirect_uri": os.getenv("REDIRECT_URI"),
        }

        response = await self._request(url, method="POST", json=data)
        self.access_token = response.get("access_token")
        _LOGGER.info(f"Access token: {self.access_token}")	

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