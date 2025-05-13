""" "Class to handle the import workflow."""

from __future__ import annotations
from collections.abc import AsyncGenerator
from datetime import datetime
import logging
from typing import Any, Self

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
        yield "Fetching accounts from TrueLayer"
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

        yield "A total of {} account(s) found".format(len(truelayer_accounts))
        for account in truelayer_accounts:
            _LOGGER.info("Account: %s", account)
            yield "Account: {}".format(account)

        yield "Fetching accounts from Firefly"

        response = await self._firefly_client.get_accounts()
        firefly_accounts = response.json()

        if response.status_code != 200:
            _LOGGER.error("Error fetching accounts from Firefly: %s", response.text)
            yield "Error fetching accounts from Firefly: {}".format(response.text)
            return

        if "data" not in firefly_accounts:
            _LOGGER.warning("No accounts found in Firefly")
            yield "No accounts found in Firefly"
            return
        firefly_accounts = firefly_accounts["data"]

        yield "A total of {} account(s) found".format(len(firefly_accounts))
        for account in firefly_accounts:
            _LOGGER.info("Account: %s", account)
            yield "Account: {}".format(account)
