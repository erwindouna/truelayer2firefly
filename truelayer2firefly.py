"""Plaid to Firefly III integration"""

from logging import config
import os
import json
import ast
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from dotenv import load_dotenv
from yarl import URL

from config import Config
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


config = Config("config.json")

@app.get("/", response_class=HTMLResponse)
async def index():
    """This is the root endpoint. For development purposes only."""

    _LOGGER.info(f"Loaded configuration: {config._config}")
   

    return Path("templates/index.html").read_text()
