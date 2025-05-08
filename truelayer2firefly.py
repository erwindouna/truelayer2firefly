from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from pathlib import Path
from yarl import URL
import logging
from contextlib import asynccontextmanager

from clients.truelayer import TrueLayerClient
from config import Config
from exceptions import TrueLayer2FireflyAuthorizationError, TrueLayer2FireflyConnectionError, TrueLayer2FireflyError, TrueLayer2FireflyTimeoutError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)

logging.getLogger("uvicorn").setLevel(logging.INFO)

config = Config("config.json")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler to initialize and close the TrueLayer client."""
    _LOGGER.info("Initializing TrueLayer client...")
    app.state.truelayer_client = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )
    _LOGGER.info("TrueLayer client initialized.")
    yield
    client = app.state.truelayer_client
    if client:
        await client.close()
        _LOGGER.info("TrueLayer client closed.")

app = FastAPI(lifespan=lifespan)

async def get_truelayer_client() -> TrueLayerClient:
    client = app.state.truelayer_client
    if not client:
        raise RuntimeError("TrueLayer client is not initialized.")
    return client

@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("templates/index.html").read_text()

@app.get("/import", response_class=HTMLResponse)
async def import_to():
    return Path("templates/import.html").read_text()

@app.get("/config")
async def get_config():
    current_config = config._config
    _LOGGER.info("Configuration successfully read.")
    return current_config

@app.get("/get-authorization-url")
async def get_authorization_url(truelayer: TrueLayerClient = Depends(get_truelayer_client)):
    """Get the authorization URL for TrueLayer."""
    auth_url = await truelayer.get_authorization_url()
    _LOGGER.info(f"Authorization URL: {auth_url}")
    return {"url": auth_url}

@app.get("/get-access-token")
async def get_access_token(truelayer: TrueLayerClient = Depends(get_truelayer_client)):
    """Get the access token from TrueLayer."""
    await truelayer.exchange_authorization_code()
    access_token = config.get("truelayer_access_token")
    _LOGGER.info("Access token successfully retrieved.")
    return {"access_token": access_token}

@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    scope = request.query_params.get("scope")

    _LOGGER.info(f"Received code: {code} and scope: {scope}")
    config.set("truelayer_code", code)
    config.set("truelayer_scope", scope)

    return HTMLResponse(content=Path("templates/index.html").read_text(), status_code=302)

@app.get("/get-tl-accounts")
async def get_tl_accounts(truelayer: TrueLayerClient = Depends(get_truelayer_client)):
    """Get the accounts from TrueLayer."""
    accounts = await truelayer.get_accounts()
    _LOGGER.info("Accounts successfully retrieved.")
    return accounts

@app.exception_handler(TrueLayer2FireflyAuthorizationError)
async def truelayer_authorization_error_handler(request: Request, exc: TrueLayer2FireflyAuthorizationError):
    _LOGGER.error("Authorization error: %s", str(exc))
    return JSONResponse(
        status_code=401,
        content={"error": "Unauthorized access", "details": str(exc)}
    )

@app.exception_handler(TrueLayer2FireflyConnectionError)
async def truelayer_connection_error_handler(request: Request, exc: TrueLayer2FireflyConnectionError):
    _LOGGER.error("Connection error: %s", str(exc))
    return JSONResponse(
        status_code=503,
        content={"error": "Connection error", "details": str(exc)}
    )

@app.exception_handler(TrueLayer2FireflyTimeoutError)
async def truelayer_timeout_error_handler(request: Request, exc: TrueLayer2FireflyTimeoutError):
    _LOGGER.error("Timeout error: %s", str(exc))
    return JSONResponse(
        status_code=504,
        content={"error": "Request timeout", "details": str(exc)}
    )

@app.exception_handler(TrueLayer2FireflyError)
async def truelayer_error_handler(request: Request, exc: TrueLayer2FireflyError):
    _LOGGER.error("TrueLayer error: %s", str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "TrueLayer error", "details": str(exc)}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    _LOGGER.exception("Unhandled exception: %s", str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "details": str(exc)}
    )