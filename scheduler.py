"""Class to handle the scheduler workflow."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

from clients.firefly import FireflyClient
from clients.truelayer import TrueLayerClient
from importer2firefly import Import2Firefly

from config import Config

_LOGGER = logging.getLogger(__name__)


class Scheduler:
    """Class to handle the scheduler workflow."""

    def __init__(self, schedule: str | None = None) -> None:
        """Initialize the Scheduler class."""
        self._config: Config = Config()
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()
        self._import_job = None
        self._schedule: str | None = schedule or self._config.get("import_schedule")

    def start(
        self, truelayer_client: TrueLayerClient, firefly_client: FireflyClient
    ) -> None:
        """Start the scheduler."""
        _LOGGER.info("Starting the scheduler, with schedule: %s", self._schedule)
        if self._schedule is None:
            _LOGGER.warning("No schedule set, not starting the scheduler")
            return

        if self._import_job:
            self._scheduler.remove_job(self._import_job.id)

        loop = asyncio.get_event_loop()

        def run_import() -> None:
            """Run the import job."""
            start_time = datetime.now()
            _LOGGER.info("Running import job, started at %s", start_time)
            importer = Import2Firefly(truelayer_client, firefly_client)

            async def consume_import():
                try:
                    async for event in importer.start_import():
                        _LOGGER.info(f"Import event: {event}")
                except Exception as e:
                    _LOGGER.error(f"Error during import: {e}")

            asyncio.run_coroutine_threadsafe(consume_import(), loop)
            end_time = datetime.now()
            elapsed_time = end_time - start_time
            _LOGGER.info("Import job completed elapsed time: %s", elapsed_time)

        self._import_job = self._scheduler.add_job(
            run_import,
            trigger=CronTrigger.from_crontab(self._schedule),
            id="import_job",
            replace_existing=True,
        )
        self._scheduler.start()
        _LOGGER.info("Scheduler started")

    def set_schedule(self, schedule: str) -> None:
        """Set the schedule for the import job."""
        self._schedule = schedule
        _LOGGER.info("Scheduler schedule set to: %s", self._schedule)

        if not schedule:
            _LOGGER.info("Disabling the scheduler")
            if self._import_job:
                self._scheduler.remove_job(self._import_job.id)
                _LOGGER.info("Scheduler job removed")
            else:
                _LOGGER.warning("No import job to remove")
            self._import_job = None
            return

        if self._import_job:
            self._scheduler.reschedule_job(
                self._import_job.id,
                trigger=CronTrigger.from_crontab(self._schedule),
            )

            if not self._scheduler.running:
                _LOGGER.info("Scheduler is not running, starting it")
                self._scheduler.start()
            _LOGGER.info("Scheduler job rescheduled to: %s", self._schedule)

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._scheduler.running:
            _LOGGER.warning("Scheduler is not running")
            return

        self._scheduler.shutdown()
        _LOGGER.info("Scheduler stopped")
