from ast import Str
import base64
from hashlib import sha256
import secrets
import string
from fastapi import FastAPI, Form, Request, Depends, params
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from yarl import URL
import logging
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware

from clients.firefly import FireflyClient
from clients.truelayer import TrueLayerClient
from config import Config
from exceptions import (
    TrueLayer2FireflyAuthorizationError,
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyError,
    TrueLayer2FireflyTimeoutError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)

logging.getLogger("uvicorn").setLevel(logging.INFO)

config = Config("config.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler to initialize and close API clients."""
    app.state.truelayer_client = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )
    _LOGGER.info("TrueLayer client initialized")

    app.state.firefly_client = FireflyClient(
        url=config.get("firefly_api_url"),
        access_token=config.get("firefly_access_token"),
    )
    _LOGGER.info("Firefly client initialized")

    yield

    if client := app.state.truelayer_client:
        await client.close()
        _LOGGER.info("TrueLayer client closed")

    if client := app.state.firefly_client:
        await client.close()
        _LOGGER.info("Firefly client closed")

    _LOGGER.info("Application shutdown complete")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(255))


async def get_truelayer_client() -> TrueLayerClient:
    client = app.state.truelayer_client
    if not client:
        raise RuntimeError("TrueLayer client is not initialized.")
    return client


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the index page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/configuration", response_class=HTMLResponse)
async def configuration(request: Request):
    """Render the configuration page."""
    return templates.TemplateResponse("configuration.html", {"request": request})


@app.post("/firefly/configuration")
async def firefly_configuration(
    request: Request, firefly_url: str = Form(...), firefly_client_id: str = Form(...)
):
    """Handle the configuration form submission."""
    _LOGGER.info("Starting configuration...")
    config.set("firefly_api_url", firefly_url)
    config.set("firefly_client_id", firefly_client_id)

    state = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(40)
    )
    code_verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(128)
    )
    code_challenge = (
        base64.urlsafe_b64encode(sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )

    session = request.session
    session["state"] = state
    session["code_verifier"] = code_verifier
    session["form_client_id"] = firefly_client_id
    session["form_base_url"] = firefly_url

    redirect_uri = str(request.url_for("firefly/callback"))
    query_params = {
        "client_id": firefly_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = (
        URL(session["form_base_url"])
        .with_path("/oauth/authorize")
        .with_query(query_params)
    )

    _LOGGER.info("Query parameters are %s", query_params)
    _LOGGER.info(f"Now redirecting to {auth_url.with_query(None)} (params omitted)")

    return RedirectResponse(str(auth_url), status_code=302)


@app.get("/firefly/callback", name="firefly/callback")
async def firefly_callback(request: Request):
    """Handle the callback from Firefly."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    session = request.session
    stored_state = session.get("state")
    stored_code_verifier = session.get("code_verifier")
    form_client_id = session.get("form_client_id")
    form_base_url = session.get("form_base_url")

    if state != stored_state:
        _LOGGER.error("State mismatch: %s != %s", state, stored_state)
        raise HTTPException(status_code=400, detail="State mismatch")

    params = {
        "grant_type": "authorization_code",
        "client_id": form_client_id,
        "redirect_uri": str(request.url_for("firefly/callback")),
        "code": code,
        "code_verifier": stored_code_verifier,
    }

    response = await FireflyClient(url=form_base_url)._request(
        uri="/oauth/token",
        method="POST",
        params=params,
    )

    _LOGGER.info("Received access token response: %s", response)
    config.set("firefly_access_token", response["access_token"])
    config.set("firefly_refresh_token", response["refresh_token"])
    config.set("firefly_expires_in", response["expires_in"])

    return RedirectResponse(
        str(request.url_for("index")),
        status_code=302,
    )


@app.get("/firefly/healthcheck")
async def firefly_healthcheck(firefly: FireflyClient = Depends(FireflyClient)):
    """Check the health of the Firefly API."""

    response = await firefly.healthcheck()
    if response.status_code != 200:
        _LOGGER.error(
            "Firefly API health check failed with status code %s", response.status_code
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "Firefly API is not healthy",
                "status_code": response.status_code,
            },
        )

    return {"status": "OK"}


@app.get("/config")
async def get_config():
    current_config = config._config
    _LOGGER.info("Configuration successfully read.")
    return current_config


@app.get("/get-authorization-url")
async def get_authorization_url(
    truelayer: TrueLayerClient = Depends(get_truelayer_client),
):
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

    return HTMLResponse(
        content=Path("templates/index.html").read_text(), status_code=302
    )


@app.get("/get-tl-accounts")
async def get_tl_accounts(truelayer: TrueLayerClient = Depends(get_truelayer_client)):
    """Get the accounts from TrueLayer."""
    accounts = await truelayer.get_accounts()
    _LOGGER.info("Accounts successfully retrieved.")
    return accounts


@app.exception_handler(TrueLayer2FireflyAuthorizationError)
async def truelayer_authorization_error_handler(
    request: Request, exc: TrueLayer2FireflyAuthorizationError
):
    _LOGGER.error("Authorization error: %s", str(exc))
    return JSONResponse(
        status_code=401, content={"error": "Unauthorized access", "details": str(exc)}
    )


@app.exception_handler(TrueLayer2FireflyConnectionError)
async def truelayer_connection_error_handler(
    request: Request, exc: TrueLayer2FireflyConnectionError
):
    _LOGGER.error("Connection error: %s", str(exc))
    return JSONResponse(
        status_code=503, content={"error": "Connection error", "details": str(exc)}
    )


@app.exception_handler(TrueLayer2FireflyTimeoutError)
async def truelayer_timeout_error_handler(
    request: Request, exc: TrueLayer2FireflyTimeoutError
):
    _LOGGER.error("Timeout error: %s", str(exc))
    return JSONResponse(
        status_code=504, content={"error": "Request timeout", "details": str(exc)}
    )


@app.exception_handler(TrueLayer2FireflyError)
async def truelayer_error_handler(request: Request, exc: TrueLayer2FireflyError):
    _LOGGER.error("TrueLayer error: %s", str(exc))
    return JSONResponse(
        status_code=500, content={"error": "TrueLayer error", "details": str(exc)}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    _LOGGER.exception("Unhandled exception: %s", str(exc))
    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "details": str(exc)}
    )
