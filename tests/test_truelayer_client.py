"""Basic tests for Truelayer2Firefly."""

import asyncio
from unittest.mock import patch

import httpx
import pytest
from aiohttp import ClientError, ClientResponse, ClientSession
from aresponses import Response, ResponsesMockServer
import respx

from clients.truelayer import TrueLayerClient
from exceptions import (
    TrueLayer2FireflyAuthorizationError,
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyTimeoutError,
)


async def test_json_request(
    aresponses: ResponsesMockServer,
    truelayer_client: TrueLayerClient,
) -> None:
    """Test JSON response is handled correctly."""
    aresponses.add(
        "localhost:9000",
        "/api/test",
        "GET",
        aresponses.Response(
            status=200, headers={"Content-Type": "application/json"}, text="{}"
        ),
    )
    response = await truelayer_client._request("test")
    assert response is not None
    await truelayer_client.close()


async def test_internal_session(mock_truelayer_api: ResponsesMockServer) -> None:
    """Test internal session is created and closed."""
    async with TrueLayerClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost/truelayer/callback",
    ) as client:
        response = await client._request("test")
        assert response


@respx.mock
async def test_timeout() -> None:
    """Test request timeout from Truelayer API."""
    # Simulate a timeout exception from httpx
    respx.get("https://api.truelayer.com/data/v1/test").mock(
        side_effect=httpx.TimeoutException("Simulated timeout")
    )

    async with TrueLayerClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost/truelayer/callback",
        request_timeout=0.1,
    ) as client:
        with pytest.raises(TrueLayer2FireflyTimeoutError):
            await client._request("test")


async def test_content_type(
    aresponses: ResponsesMockServer,
    truelayer_client: TrueLayerClient,
) -> None:
    """Test request content type error from Truelayer API."""
    aresponses.add(
        "localhost:9000",
        "/api/test",
        "GET",
        aresponses.Response(
            status=200,
            headers={"Content-Type": "blabla/blabla"},
        ),
    )
    with pytest.raises(TrueLayer2FireflyConnectionError):
        assert await truelayer_client._request("test")


async def test_client_error() -> None:
    """Test request client error from Autarco API."""
    async with ClientSession() as session:
        client = TrueLayerClient(
            api_url="http://localhost:9000/api", api_key="test_api_key", session=session
        )
        with (
            patch.object(
                session,
                "request",
                side_effect=ClientError,
            ),
            pytest.raises(TrueLayer2FireflyConnectionError),
        ):
            assert await client._request("test")
        await session.close()


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, TrueLayer2FireflyAuthorizationError),
        (500, TrueLayer2FireflyConnectionError),
    ],
)
async def test_response_status(
    aresponses: ResponsesMockServer,
    truelayer_client: TrueLayerClient,
    status_code: int,
    expected_exception: type[Exception],
) -> None:
    """Test HTTP response status handling."""
    aresponses.add(
        "localhost:9000",
        "/api/test",
        "GET",
        aresponses.Response(text="Error response", status=status_code),
    )
    with pytest.raises(expected_exception):
        await truelayer_client._request("test")
