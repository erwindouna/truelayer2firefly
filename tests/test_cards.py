"""Tests for TrueLayer card support (get_cards, get_card_transactions, get_accounts_and_cards)."""

import pytest
import respx
from httpx import Response

from clients.truelayer import TrueLayerClient
from exceptions import TrueLayer2FireflyConnectionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACCOUNTS_URL = "https://api.truelayer.com/data/v1/accounts"
CARDS_URL = "https://api.truelayer.com/data/v1/cards"

SAMPLE_ACCOUNT = {
    "account_id": "acc-001",
    "account_number": {"iban": "GB00TEST0000000001"},
    "display_name": "Current Account",
    "currency": "GBP",
    "account_type": "TRANSACTION",
    "provider": {"provider_id": "mock-bank"},
}

SAMPLE_CARD = {
    "account_id": "card-001",
    "display_name": "AMEX Gold",
    "card_type": "AMEX",
    "currency": "GBP",
    "card_number": {"last_four_digits": "1234", "number_type": "CREDIT"},
    "provider": {"provider_id": "mock-amex"},
}

SAMPLE_CARD_TXN = {
    "transaction_id": "txn-c-001",
    "timestamp": "2024-01-15T10:00:00Z",
    "description": "Coffee Shop",
    "transaction_type": "DEBIT",
    "amount": -4.50,
    "currency": "GBP",
    "meta": {},
}


# ---------------------------------------------------------------------------
# get_cards
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_cards_success() -> None:
    """get_cards returns the raw API response for a successful request."""
    respx.get(CARDS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_CARD]})
    )

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        response = await client.get_cards()

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert data["results"][0]["account_id"] == "card-001"


@respx.mock
async def test_get_cards_error_raises() -> None:
    """get_cards raises TrueLayer2FireflyConnectionError on HTTP errors."""
    respx.get(CARDS_URL).mock(return_value=Response(501, text="Not Implemented"))

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        with pytest.raises(TrueLayer2FireflyConnectionError):
            await client.get_cards()


# ---------------------------------------------------------------------------
# get_card_transactions
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_card_transactions_success() -> None:
    """get_card_transactions returns transactions for a given card ID."""
    card_id = "card-001"
    respx.get(f"https://api.truelayer.com/data/v1/cards/{card_id}/transactions").mock(
        return_value=Response(200, json={"results": [SAMPLE_CARD_TXN]})
    )

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        response = await client.get_card_transactions(card_id)

    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["transaction_id"] == "txn-c-001"


# ---------------------------------------------------------------------------
# get_accounts_and_cards — combined helper
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_accounts_and_cards_account_only() -> None:
    """When only /accounts is supported, returns only account entities."""
    respx.get(ACCOUNTS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_ACCOUNT]})
    )
    respx.get(CARDS_URL).mock(return_value=Response(501, text="Not Implemented"))

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        results = await client.get_accounts_and_cards()

    assert len(results) == 1
    assert results[0]["kind"] == "account"
    assert results[0]["account_id"] == "acc-001"


@respx.mock
async def test_get_accounts_and_cards_card_only() -> None:
    """When only /cards is supported (e.g. AMEX), returns only card entities."""
    respx.get(ACCOUNTS_URL).mock(return_value=Response(501, text="Not Implemented"))
    respx.get(CARDS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_CARD]})
    )

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        results = await client.get_accounts_and_cards()

    assert len(results) == 1
    assert results[0]["kind"] == "card"
    assert results[0]["account_id"] == "card-001"


@respx.mock
async def test_get_accounts_and_cards_both_supported() -> None:
    """When both endpoints work, returns both accounts and cards."""
    respx.get(ACCOUNTS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_ACCOUNT]})
    )
    respx.get(CARDS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_CARD]})
    )

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        results = await client.get_accounts_and_cards()

    assert len(results) == 2
    kinds = {r["kind"] for r in results}
    assert kinds == {"account", "card"}


@respx.mock
async def test_get_accounts_and_cards_both_fail_raises() -> None:
    """When both endpoints fail, raises TrueLayer2FireflyConnectionError."""
    respx.get(ACCOUNTS_URL).mock(return_value=Response(503, text="Service Unavailable"))
    respx.get(CARDS_URL).mock(return_value=Response(503, text="Service Unavailable"))

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        with pytest.raises(TrueLayer2FireflyConnectionError):
            await client.get_accounts_and_cards()


@respx.mock
async def test_get_accounts_and_cards_kind_field_set() -> None:
    """Each entity returned by get_accounts_and_cards has the 'kind' field set."""
    respx.get(ACCOUNTS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_ACCOUNT, SAMPLE_ACCOUNT]})
    )
    respx.get(CARDS_URL).mock(
        return_value=Response(200, json={"results": [SAMPLE_CARD]})
    )

    async with TrueLayerClient(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="http://localhost/cb",
    ) as client:
        results = await client.get_accounts_and_cards()

    assert all("kind" in r for r in results)
    account_results = [r for r in results if r["kind"] == "account"]
    card_results = [r for r in results if r["kind"] == "card"]
    assert len(account_results) == 2
    assert len(card_results) == 1
