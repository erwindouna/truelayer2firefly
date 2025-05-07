"""Plaid to Firefly III integration"""

from logging import config
import os
import json
import ast
from typing import Any

from annotated_types import T
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from dotenv import load_dotenv
from yarl import URL


from clients.truelayer import TrueLayerClient
from config import Config
import logging

logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level to DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)

# Ensure Uvicorn logs are also displayed
logging.getLogger("uvicorn").setLevel(logging.DEBUG)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


config = Config("config.json")

@app.get("/", response_class=HTMLResponse)
async def index():
    """This is the root endpoint. For development purposes only."""

    _LOGGER.info(f"Loaded configuration: {config._config}")
   

    return Path("templates/index.html").read_text()

async def start_app():
    """Start the app and load the configuration"""
    _LOGGER.info("Starting TrueLayer2Firefly app")
    config._load()
    _LOGGER.info(f"Loaded configuration: {config._config}")
    truelayer = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )

if __name__ == "__main__":
    import asyncio

    _LOGGER.info("Running start_app in debug mode")
    asyncio.run(start_app())