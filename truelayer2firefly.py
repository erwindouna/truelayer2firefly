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

from exceptions import TrueLayer2FireflyConnectionError

logging.basicConfig(
    level=logging.DEBUG,
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
    return Path("templates/index.html").read_text()

@app.get("/import", response_class=HTMLResponse)
async def import_to():
    """Import endpoint for TrueLayer2Firefly"""
    return Path("templates/import.html").read_text()

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

    _LOGGER.info("TrueLayer client initialized")
    try:
        auth_url = await truelayer.get_authorization_url()
    except TrueLayer2FireflyConnectionError as e:
        _LOGGER.exception("Connection error occurred while getting authorization URL")
        return
    
    _LOGGER.info(f"Authorization URL: {auth_url}")

@app.get("/config")
async def get_config():
    """Get the config file"""
    try:
        current_config = config._config
        _LOGGER.info("Configuration successfully read.")
        return current_config
    except Exception as e:
        _LOGGER.error(f"Failed to read configuration: {e}")
        return {"error": "Failed to read configuration."}, 500
    
@app.get("/get-authorization-url")
async def get_authorization_url():
    """Get the authorization URL for TrueLayer"""
    truelayer = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )

    auth_url = await truelayer.get_authorization_url()
    _LOGGER.info(f"Authorization URL: {auth_url}")
    return {"url": auth_url}

@app.get("/get-access-token")
async def get_access_token():
    """Get the access token from TrueLayer"""
    truelayer = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )

    code = config.get("truelayer_code")
    scope = config.get("truelayer_scope")

    if not code or not scope:
        return {"error": "Code or scope not set in configuration."}, 400

    try:
        access_token = await truelayer.exchange_authorization_code()
        _LOGGER.info(f"Access token: {access_token}")
        return {"access_token": access_token}
    except TrueLayer2FireflyConnectionError as e:
        _LOGGER.exception("Connection error occurred while getting access token")
        return {"error": str(e)}, 500

@app.get("/callback")
async def callback(request: Request):
    """Handle the callback from TrueLayer"""
    code = request.query_params.get("code")
    scope = request.query_params.get("scope")

    _LOGGER.info(f"Received code: {code} and scope: {scope}")
    config.set("truelayer_code", code)
    config.set("truelayer_scope", scope)

    return HTMLResponse(content=Path("templates/index.html").read_text(), status_code=302)


if __name__ == "__main__":
    import asyncio

    asyncio.run(start_app())