""" "Class to handle the import workflow."""

from __future__ import annotations
from collections.abc import AsyncGenerator
from datetime import datetime
import logging
from typing import Any, Self

from attr import attributes

from clients.firefly import FireflyClient
from clients.truelayer import TrueLayerClient
from config import Config

_LOGGER = logging.getLogger(__name__)


class Import2Firefly:
    """Class to handle the import workflow."""

    def __init__(self, truelayer: TrueLayerClient, firefly: FireflyClient) -> None:
        """Initialize the Import class."""
        self._config: Config = Config()
        self._truelayer_client = truelayer
        self._firefly_client = firefly

        self.start_time = datetime.now()
        self.end_time = None

    async def start_import(self) -> AsyncGenerator[Any, Any]:
        """Start the import process."""
        _LOGGER.info("Starting import process")
        yield "TrueLayer: Fetching accounts from TrueLayer"
        response = await self._truelayer_client.get_accounts()
        truelayer_accounts = response.json()

        if response.status_code != 200:
            _LOGGER.error("Error fetching accounts from TrueLayer: %s", response.text)
            yield "Error fetching accounts from TrueLayer: {}".format(response.text)
            return

        if "results" not in truelayer_accounts:
            _LOGGER.warning("No accounts found in TrueLayer")
            yield "No accounts found in TrueLayer"
            return

        truelayer_accounts = truelayer_accounts["results"]
        for account in truelayer_accounts:
            _LOGGER.info("Account: %s", account)
            yield "TrueLayer account: {}".format(account)
        yield "TrueLayer: A total of {} account(s) found".format(
            len(truelayer_accounts)
        )

        yield "Firefly: Fetching accounts from Firefly"

        firefly_accounts = await self._firefly_client.get_account_paginated()

        for account in firefly_accounts:
            _LOGGER.info("Account: %s", account)
            yield "Firefly account: {}".format(account)
        yield "Firefly: A total of {} account(s) found".format(len(firefly_accounts))

        yield "Matching account(s) between TrueLayer and Firefly"
        for truelayer_account in truelayer_accounts:
            import_account: dict[str, Any] = {}
            for firefly_account in firefly_accounts:
                if (
                    truelayer_account["account_number"]["iban"]
                    == firefly_account["attributes"]["iban"]
                ):
                    yield "Matching account found: TrueLayer {} and Firefly {}".format(
                        truelayer_account["account_number"]["iban"],
                        firefly_account["attributes"]["iban"],
                    )

                    if firefly_account["attributes"]["account_role"] == "defaultAsset":
                        import_account = firefly_account
                        yield "Firefly account is a default asset account, let's continue"
                        break

            if not import_account:
                yield "No matching account found for TrueLayer account {}".format(
                    truelayer_account["account_number"]["iban"]
                )
                continue

            yield "TrueLayer: Fetching transactions for account {}. This can take a few seconds...".format(
                truelayer_account["account_number"]["iban"]
            )
            transactions = await self._truelayer_client.get_transactions(
                truelayer_account["account_id"]
            )

            if transactions.status_code != 200:
                _LOGGER.error(
                    "Error fetching transactions from TrueLayer: %s", transactions.text
                )
                yield "Error fetching transactions from TrueLayer: {}".format(
                    transactions.text
                )
                continue
            if "results" not in transactions.json():
                _LOGGER.warning("No transactions found in TrueLayer")
                yield "No transactions found in TrueLayer"
                continue
            transactions = transactions.json()["results"]
            for transaction in transactions:
                _LOGGER.info("Transaction: %s", transaction)
                yield "TrueLayer transaction: {}".format(transaction)
            yield "TrueLayer: A total of {} transaction(s) found".format(
                len(transactions)
            )
