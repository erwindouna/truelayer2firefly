"""Class to handle the import workflow."""

from __future__ import annotations
import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime
import logging
from typing import Any


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

        yield "TrueLayer: Fetching accounts from TrueLayer"
        response = await self._truelayer_client.get_accounts()
        await asyncio.sleep(0)

        if response.status_code != 200:
            yield f"Error fetching accounts from TrueLayer: {response.text}"
            return

        truelayer_accounts = response.json()
        if "results" not in truelayer_accounts:
            yield "No accounts found in TrueLayer"
            return

        truelayer_accounts = truelayer_accounts["results"]
        for account in truelayer_accounts:
            yield f"TrueLayer account: {account['account_id']} - {account['account_number'].get('iban')}"
            await asyncio.sleep(0)

        yield f"TrueLayer: A total of {len(truelayer_accounts)} account(s) found"
        await asyncio.sleep(0)

        yield "Firefly: Fetching accounts from Firefly"
        firefly_accounts = await self._firefly_client.get_account_paginated()
        yield f"Firefly: A total of {len(firefly_accounts)} account(s) found"

        yield "Matching account(s) between TrueLayer and Firefly"

        for truelayer_account in truelayer_accounts:
            import_account: dict[str, Any] = {}
            tr_iban = truelayer_account["account_number"].get("iban")
            yield f"Checking matches for TrueLayer account {tr_iban}"

            for firefly_account in firefly_accounts:
                ff_iban = firefly_account["attributes"].get("iban")
                if tr_iban == ff_iban:
                    yield f"Matching account found: {tr_iban}"
                    if (
                        firefly_account["attributes"].get("account_role")
                        == "defaultAsset"
                    ):
                        import_account = firefly_account
                        yield "Firefly account is a default asset account, let's continue"
                        break
                    else:
                        yield "Firefly account matched, but is not a default asset"
            else:
                yield f"No matching Firefly account found for IBAN {tr_iban}"
                continue

            yield f"TrueLayer: Fetching transactions for {tr_iban}..."
            transactions = await self._truelayer_client.get_transactions(
                truelayer_account["account_id"]
            )

            if transactions.status_code != 200:
                yield f"Error fetching transactions from TrueLayer: {transactions.text}"
                continue

            parsed = transactions.json()
            if "results" not in parsed:
                yield "No transactions found in TrueLayer"
                continue

            txns = parsed["results"]
            yield f"TrueLayer: A total of {len(txns)} transaction(s) found"
            yield "TrueLayer: Matching transactions to Firefly account"

            matching = 0
            unmatching = 0
            newly_created = 0
            total_transactions = len(txns)
            for i, txn in enumerate(txns, start=1):
                cp_iban = txn.get("meta", {}).get("counter_party_iban")
                transaction_type = (
                    "debit" if txn["transaction_type"].lower() == "debit" else "credit"
                )
                linked_account = None

                if cp_iban is not None:
                    for firefly_account in firefly_accounts:
                        if (
                            transaction_type == "debit"
                            and firefly_account["attributes"]["type"] != "expense"
                        ):
                            continue
                        if (
                            transaction_type == "credit"
                            and firefly_account["attributes"]["type"] != "revenue"
                        ):
                            continue

                        if cp_iban == firefly_account["attributes"].get("iban"):
                            yield f"Matching account found via IBAN: {txn['description']} - {cp_iban}"
                            linked_account = firefly_account
                            matching += 1
                            break

                    if linked_account is None:
                        yield f"No match, still a valid IBAN. Creating a new account: {txn} - {cp_iban}"
                        response = await self._firefly_client.create_account(
                            {
                                "name": txn.get("meta", {}).get(
                                    "counter_party_preferred_name"
                                )
                                or "Unnamed",
                                "iban": cp_iban,
                                "type": (
                                    "revenue"
                                    if transaction_type == "credit"
                                    else "expense"
                                ),
                            }
                        )
                        if response.status_code != 200:
                            yield f"Error creating account in Firefly: {response.text}"
                            continue
                        yield f"New account created: {txn.get('meta', {}).get('counter_party_preferred_name')} - {cp_iban}"
                        linked_account = response.json()["data"]
                        newly_created += 1
                else:
                    unmatching += 1
                    # TODO: find the unknown destination account
                    yield f"Transaction has no IBAN: {txn['description']}"

                # Ensure the amount is always positive
                amount = abs(txn["amount"])
                import_transaction = {
                    "error_if_duplicate_hash": True,
                    "apply_rules": True,
                    "fire_webhooks": True,
                    "group_title": "Split transaction title.",
                    "transactions": [
                        {
                            "description": txn["description"],
                            "date": txn["timestamp"],
                            "amount": amount,
                            "type": (
                                "revenue"
                                if transaction_type == "deposit"
                                else "withdrawal"
                            ),
                            "destination_id": (
                                None if linked_account is None else linked_account["id"]
                            ),
                            "destination_name": (
                                "(unknown revenue account)"
                                if linked_account is None
                                and transaction_type == "deposit"
                                else (
                                    "(unknown destination account)"
                                    if linked_account is None
                                    else linked_account["attributes"]["name"]
                                )
                            ),
                            "source_id": import_account["id"],
                            "source_name": import_account["attributes"]["name"],
                            "account_id": import_account["id"],
                            "linked_account_id": txn["transaction_id"],
                        }
                    ],
                }
                try:
                    response = await self._firefly_client.create_transaction(
                        import_transaction
                    )
                except Exception as e:
                    yield f"Error creating transaction in Firefly: {e}"
                if response.status_code == 200:
                    yield f"Transaction created: {txn['description']} - {txn['amount']} - {txn['timestamp']}"
                elif response.status_code == 442:
                    yield f"Transaction already exists: {txn['description']} - {txn['amount']} - {txn['timestamp']}"
                else:
                    yield f"Error creating transaction in Firefly: {response.text}"
                await asyncio.sleep(0)

                yield {
                    "type": "progress",
                    "data": {
                        "account": tr_iban,
                        "current": i,
                        "total": total_transactions,
                    },
                }
                await asyncio.sleep(0.05)

            yield f"Report: {matching} matching and {unmatching} unmatching and {newly_created} newly created accounts(s)"
            await asyncio.sleep(0)
