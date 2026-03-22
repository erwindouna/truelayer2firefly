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
from exceptions import TrueLayer2FireflyConnectionError
from truelayer_connections import (
    activate_truelayer_connection,
    get_truelayer_connections,
    upsert_active_truelayer_connection,
)

_LOGGER = logging.getLogger(__name__)


class Import2Firefly:
    """Class to handle the import workflow."""

    def __init__(self) -> None:
        """Initialize the Import class."""
        self._config: Config = Config()
        self._truelayer_client: TrueLayerClient = TrueLayerClient()
        self._firefly_client: FireflyClient = FireflyClient()

        self.start_time = datetime.now()
        self.end_time = None

    @staticmethod
    def _card_labels(source: dict[str, Any]) -> list[str]:
        """Return card labels used for matching and logging."""
        display_name = source.get("display_name", source["account_id"])
        labels: list[str] = []

        last_four_digits = source.get("card_number", {}).get("last_four_digits")
        if last_four_digits:
            labels.append(f"{display_name} ****{last_four_digits}")

        labels.append(display_name)
        return labels

    async def start_import(self) -> AsyncGenerator[Any, Any]:
        """Start the import process."""

        truelayer_connections = get_truelayer_connections(self._config)
        if not truelayer_connections:
            yield "No TrueLayer connections found. Please connect at least one bank/card provider first."
            return

        yield f"TrueLayer: A total of {len(truelayer_connections)} connection(s) configured"
        await asyncio.sleep(0)

        yield "Firefly: Fetching accounts from Firefly"
        firefly_accounts = await self._firefly_client.get_account_paginated()
        yield f"Firefly: A total of {len(firefly_accounts)} account(s) found"

        total_sources = 0

        for idx, truelayer_connection in enumerate(truelayer_connections, start=1):
            activate_truelayer_connection(self._config, truelayer_connection)
            connection_label = truelayer_connection.get("credentials_id") or f"connection-{idx}"
            yield f"TrueLayer: Processing connection {idx}/{len(truelayer_connections)} ({connection_label})"
            yield "TrueLayer: Fetching accounts and cards from TrueLayer"
            try:
                truelayer_sources = await self._truelayer_client.get_accounts_and_cards()
            except TrueLayer2FireflyConnectionError as err:
                yield f"Error fetching accounts/cards from TrueLayer connection {connection_label}: {err}"
                continue

            # Persist refreshed tokens when the client has refreshed them during requests.
            upsert_active_truelayer_connection(self._config)

            await asyncio.sleep(0)

            if not truelayer_sources:
                yield f"No accounts or cards found for connection {connection_label}"
                continue

            total_sources += len(truelayer_sources)

            for source in truelayer_sources:
                source_kind = source["kind"]
                if source_kind == "card":
                    source_label = self._card_labels(source)[0]
                else:
                    source_label = source["account_number"].get("iban") or source["account_id"]
                yield f"TrueLayer {source_kind}: {source['account_id']} - {source_label}"
                await asyncio.sleep(0)

            yield f"TrueLayer: A total of {len(truelayer_sources)} source(s) found in {connection_label}"
            await asyncio.sleep(0)

            yield "Matching source(s) between TrueLayer and Firefly"

            for truelayer_source in truelayer_sources:
                import_account: dict[str, Any] = {}
                source_kind = truelayer_source["kind"]

                if source_kind == "card":
                    card_labels = self._card_labels(truelayer_source)
                    tr_label = card_labels[0]
                    tr_iban = None
                else:
                    card_labels = []
                    tr_iban = truelayer_source["account_number"].get("iban")
                    tr_label = tr_iban or truelayer_source["account_id"]

                yield f"Checking matches for TrueLayer {source_kind}: {tr_label}"

                for firefly_account in firefly_accounts:
                    if source_kind == "card":
                        # Match cards by account name. We try a precise label first, then legacy display_name.
                        ff_name = firefly_account["attributes"].get("name", "")
                        matched = ff_name in card_labels
                    else:
                        # Match accounts by IBAN (existing behaviour)
                        ff_iban = firefly_account["attributes"].get("iban")
                        matched = tr_iban == ff_iban

                    if matched:
                        yield f"Matching account found: {tr_label}"
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
                    yield f"No matching Firefly account found for {tr_label}"
                    continue

                yield f"TrueLayer: Fetching transactions for {tr_label}..."
                if source_kind == "card":
                    transactions = await self._truelayer_client.get_card_transactions(
                        truelayer_source["account_id"]
                    )
                else:
                    transactions = await self._truelayer_client.get_transactions(
                        truelayer_source["account_id"]
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
                    cp_name = txn.get("meta", {}).get("counter_party_preferred_name")
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

                            # Check if the IBAN matches
                            if cp_iban == firefly_account["attributes"].get("iban"):
                                yield f"Matching account found via IBAN: {txn['description']} - {cp_iban}"
                                linked_account = firefly_account
                                matching += 1
                                break

                            # Check if the name matches, as a final fallback
                            # This is not preferred, but can be used if the IBAN is not available or when the  account uses multiple IBANs
                            # Firefly doesn't allow to create multiple accounts with the same name, so this should be safe
                            if cp_name is not None and cp_name == firefly_account[
                                "attributes"
                            ].get("name"):
                                yield f"Matching account found via name: {txn['description']} - {cp_name}"
                                linked_account = firefly_account
                                matching += 1
                                break

                        if linked_account is None:
                            account_type = (
                                "revenue" if transaction_type == "credit" else "expense"
                            )

                            yield f"No match, still a valid IBAN. Creating a new account: {txn} - {cp_iban} - {account_type}"
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

                            yield "Firefly: Enforcing refresh accounts from Firefly"
                            firefly_accounts = (
                                await self._firefly_client.get_account_paginated()
                            )
                            yield f"Firefly: A total of {len(firefly_accounts)} account(s) found"
                    else:
                        unmatching += 1
                        yield f"Transaction has no IBAN: {txn['description']}"

                    # Ensure the amount is always positive
                    amount = abs(txn["amount"])
                    import_transaction = {
                        "error_if_duplicate_hash": True,
                        "apply_rules": True,
                        "fire_webhooks": True,
                        "transactions": [
                            {
                                "description": txn["description"],
                                "date": txn["timestamp"],
                                "amount": amount,
                                "type": (
                                    "deposit"
                                    if transaction_type == "credit"
                                    else "withdrawal"
                                ),
                                # SWAP for deposit: asset account is destination, revenue account is source
                                "destination_id": (
                                    import_account["id"]
                                    if transaction_type == "credit"
                                    else (
                                        None
                                        if linked_account is None
                                        else linked_account["id"]
                                    )
                                ),
                                "destination_name": (
                                    import_account["attributes"]["name"]
                                    if transaction_type == "credit"
                                    else (
                                        "(unknown expense account)"
                                        if linked_account is None
                                        else linked_account["attributes"]["name"]
                                    )
                                ),
                                "source_id": (
                                    (
                                        None
                                        if linked_account is None
                                        else linked_account["id"]
                                    )
                                    if transaction_type == "credit"
                                    else import_account["id"]
                                ),
                                "source_name": (
                                    (
                                        "(unknown revenue account)"
                                        if linked_account is None
                                        else linked_account["attributes"]["name"]
                                    )
                                    if transaction_type == "credit"
                                    else import_account["attributes"]["name"]
                                ),
                                "account_id": import_account["id"],
                                "linked_account_id": (
                                    f"{source_kind}:{truelayer_source['account_id']}:{txn['transaction_id']}"
                                ),
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
                            "account": tr_label,
                            "current": i,
                            "total": total_transactions,
                        },
                    }
                    await asyncio.sleep(0.05)

                yield f"Report: {matching} matching and {unmatching} unmatching and {newly_created} newly created accounts(s)"
                await asyncio.sleep(0)

        yield f"TrueLayer: Completed import processing for {total_sources} source(s) across all connections"

