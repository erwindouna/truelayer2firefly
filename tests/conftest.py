"""Conftest for the Truelayer2Firefly tests."""

from collections.abc import AsyncGenerator, Generator

import pytest
import respx
from httpx import Response


from clients.truelayer import TrueLayerClient
from clients.firefly import FireflyClient


@pytest.fixture(name="truelayer_client")
async def truelayer_client() -> AsyncGenerator[TrueLayerClient, None]:
    """Return a Truelayer client."""
    async with TrueLayerClient(
        access_token="test_access_token",
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="test_redirect_uri",
    ) as truelayer_client:
        yield truelayer_client


@pytest.fixture(name="firefly_client")
async def firefly_client() -> AsyncGenerator[FireflyClient, None]:
    """Return a Firefly client."""
    async with FireflyClient(
        access_token="test_access_token",
        url="https://api.firefly.com",
    ) as firefly_client:
        yield firefly_client


@pytest.fixture
def mock_truelayer_api() -> Generator[respx.MockRouter, None, None]:
    """Fixture to mock TrueLayer API responses using respx."""
    with respx.mock(base_url="https://api.truelayer.com/data/v1") as respx_mock:
        respx_mock.get("/test").mock(
            return_value=Response(200, json={"test": "response"})
        )
        yield respx_mock
