"""Class to handle TrueLayer API calls."""

from datetime import datetime
import logging

import time
from typing import Any, Self
import humanize

import jwt
import httpx
from pytest import param
from yarl import URL
from config import Config

from exceptions import (
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyError,
    TrueLayer2FireflyTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class TrueLayerClient:
    """TrueLayer client for making API calls"""

    def __init__(
        self,
        request_timeout: float = 10.0,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ):
        """Initialize the TrueLayer client"""
        self.client_id: str | None = client_id
        self.client_secret: str | None = client_secret
        self.redirect_uri: str | None = redirect_uri
        self.access_token: str | None = None

        self._config = Config()
        self._request_timeout = request_timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def lifetime(self) -> str | None:
        """Get the lifetime of the access token"""
        if not self._config.get("expiration_date"):  # TODO: Fix this
            _LOGGER.warning("Expiration date not set in the config")
            return None
        return humanize.naturaldelta(
            datetime.fromtimestamp(self._config.get("expiration_date")) - datetime.now()
        )

    @property
    def import_accounts(self) -> list[dict[str, str]]:
        """Get the import accounts"""
        return self._import_accounts

    @property
    def import_transactions(self) -> list[dict[str, str]]:
        """Get the import transactions"""
        return self._import_transactions

    async def _request(
        self,
        uri: str,
        *,
        auth: bool = False,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make a request to the TrueLayer API"""
        self.access_token = self._config.get("truelayer_access_token")
        self.client_id = self._config.get("truelayer_client_id")
        self.client_secret = self._config.get("truelayer_client_secret")
        self.redirect_uri = self._config.get("truelayer_redirect_uri")

        if auth:
            url = str(URL("https://auth.truelayer.com").join(URL(uri)))
        else:
            url = str(
                URL("https://api.truelayer.com/data/v1/").join(URL(uri.lstrip("/")))
            )

        headers = {
            "Accept": "application/json",
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
            if method == "POST" and auth:
                _LOGGER.debug("Sending POST request with form-encoded data")
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=params,
                )
            else:
                if self._config.get("truelayer_access_token"):
                    headers["Authorization"] = (
                        f"Bearer {self._config.get('truelayer_access_token')}"
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
        if "application/json" not in content_type:
            msg = "Unexpected content type response from the TrueLayer API"
            raise TrueLayer2FireflyError(
                msg,
                {"Content-Type": content_type, "response": response.text},
            )

        return response.json()

    async def get_authorization_url(self) -> str:
        """Get the authorization URL for TrueLayer."""

        params = {
            "response_type": "code",
            "client_id": self._config.get("truelayer_client_id"),
            "redirect_uri": self._config.get("truelayer_redirect_uri"),
            "nonce": int(time.time()),
            "scope": "info accounts balance cards transactions direct_debits standing_orders offline_access",
            "providers": (
                "uk-ob-all uk-oauth-all nl-xs2a-all de-xs2a-all fr-xs2a-all ie-xs2a-all "
                "es-xs2a-all it-xs2a-all pt-xs2a-all be-xs2a-all fi-xs2a-all dk-xs2a-all "
                "no-xs2a-all pl-xs2a-all at-xs2a-all ro-xs2a-all lt-xs2a-all lv-xs2a-all ee-xs2a-all"
            ),
        }

        return str(URL("https://auth.truelayer.com").with_query(params))

    async def exchange_authorization_code(self) -> None:
        """Exchange the authorization code for an access token."""
        params = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": self._config.get("truelayer_code"),
        }

        response = await self._request(
            uri="/connect/token",
            auth=True,
            method="POST",
            params=params,
        )

        _LOGGER.info("Received access token response: %s", response)

        self._config.set("truelayer_access_token", response["access_token"])
        self._config.set("truelayer_refresh_token", response["refresh_token"])

        self.access_token = response["access_token"]
        self.refresh_token = response["refresh_token"]

        await self._extract_info_from_token()

    async def _extract_info_from_token(self) -> None:
        """Extract information from the access token."""
        _LOGGER.info("Extracting information from access token: %s", self.access_token)
        decoded = jwt.decode(self.access_token, options={"verify_signature": False})
        self._config.set("credentials_id", decoded["sub"])
        self._config.set("expiration_date", decoded["exp"])

    async def get_accounts(self) -> dict[str, Any]:
        """Get the accounts from TrueLayer."""
        response = await self._request(
            uri="accounts",
            method="GET",
        )

        _LOGGER.info("Received accounts response: %s", response)

        if "accounts" not in response:
            raise TrueLayer2FireflyError("No accounts found in the response")

        return response["accounts"]

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
