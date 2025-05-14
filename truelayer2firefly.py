import base64
from collections.abc import AsyncGenerator
from hashlib import sha256
import json
import secrets
import string
from fastapi import FastAPI, Form, Request, Depends, params
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from yarl import URL
import logging
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware

from clients.firefly import FireflyClient
from clients.truelayer import TrueLayerClient
from config import Config
from exception_handlers import (
    truelayer_authorization_error_handler,
    truelayer_connection_error_handler,
    truelayer_timeout_error_handler,
    truelayer_error_handler,
    generic_exception_handler,
)
from exceptions import (
    TrueLayer2FireflyAuthorizationError,
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyError,
    TrueLayer2FireflyTimeoutError,
)
from importer2firefly import Import2Firefly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)

logging.getLogger("uvicorn").setLevel(logging.INFO)

config = Config()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler to initialize and close API clients."""
    application.state.truelayer_client = TrueLayerClient(
        client_id=config.get("truelayer_client_id"),
        client_secret=config.get("truelayer_client_secret"),
        redirect_uri=config.get("truelayer_redirect_uri"),
    )
    _LOGGER.info("TrueLayer client initialized")

    application.state.firefly_client = FireflyClient(
        url=config.get("firefly_api_url"),
        access_token=config.get("firefly_access_token"),
    )
    _LOGGER.info("Firefly client initialized")

    yield

    if client := application.state.truelayer_client:
        await client.close()
        _LOGGER.info("TrueLayer client closed")

    if client := application.state.firefly_client:
        await client.close()
        _LOGGER.info("Firefly client closed")

    _LOGGER.info("Application shutdown complete")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(255))


async def get_truelayer_client() -> TrueLayerClient:
    """Get the TrueLayer client from the application state."""
    client = app.state.truelayer_client
    if not client:
        raise RuntimeError("TrueLayer client is not initialized.")
    return client


async def get_firefly_client() -> FireflyClient:
    """Get the Firefly client from the application state."""
    client = app.state.firefly_client
    if not client:
        raise RuntimeError("Firefly client is not initialized.")
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

    # Dynamically construct the redirect URI, useful for reverse proxies
    host = request.headers.get("X-Forwarded-Host", request.headers.get("Host"))
    scheme = request.headers.get("X-Forwarded-Proto", "http")
    redirect_uri = f"{scheme}://{host}/firefly/callback"
    session["redirect_uri"] = redirect_uri

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
    _LOGGER.info("Now redirecting to %s", auth_url)

    return RedirectResponse(str(auth_url), status_code=302)


@app.get("/firefly/callback", name="firefly/callback")
async def firefly_callback(
    request: Request, firefly: FireflyClient = Depends(FireflyClient)
):
    """Handle the callback from Firefly."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    session = request.session
    stored_state = session.get("state")
    stored_code_verifier = session.get("code_verifier")
    form_client_id = session.get("form_client_id")
    redirect_uri = session.get("redirect_uri")

    if state != stored_state:
        _LOGGER.error("State mismatch: %s != %s", state, stored_state)
        raise HTTPException(status_code=400, detail="State mismatch")

    params = {
        "grant_type": "authorization_code",
        "client_id": form_client_id,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": stored_code_verifier,
    }

    response = await firefly._request(
        uri="oauth/token",
        method="POST",
        auth=True,
        params=params,
    )

    response = response.json()

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

    if not firefly.access_token:
        _LOGGER.warning("Firefly access token is not set")
        return JSONResponse(
            status_code=503,
            content={"error": "Firefly API access token is not set"},
        )

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


@app.post("/truelayer/configuration")
async def truelayer_configuration(
    truelayer: TrueLayerClient = Depends(get_truelayer_client),
    truelayer_client_id: str = Form(...),
    truelayer_client_secret: str = Form(...),
    truelayer_redirect_uri: str = Form(...),
):
    """Handle the TrueLayer configuration form submission."""
    _LOGGER.info("Starting TrueLayer configuration...")
    config.set("truelayer_client_id", truelayer_client_id)
    config.set("truelayer_client_secret", truelayer_client_secret)
    config.set("truelayer_redirect_uri", truelayer_redirect_uri)

    auth_url = await truelayer.get_authorization_url()
    _LOGGER.info("Authorization URL: %s", auth_url)

    return RedirectResponse(str(auth_url), status_code=302)


@app.get("/truelayer/get-access-token", name="truelayer/get-access-token")
async def get_access_token(
    request: Request, truelayer: TrueLayerClient = Depends(get_truelayer_client)
):
    """Get the access token from TrueLayer."""
    await truelayer.exchange_authorization_code()
    _LOGGER.info("Access token successfully retrieved.")

    return RedirectResponse(
        str(request.url_for("index")),
        status_code=302,
    )


@app.get("/truelayer/callback")
async def callback(request: Request) -> None:
    """Handle the callback from TrueLayer."""
    code = request.query_params.get("code")
    scope = request.query_params.get("scope")

    _LOGGER.info("Received code: %s and scope: %s", code, scope)
    config.set("truelayer_code", code)
    config.set("truelayer_scope", scope)

    return RedirectResponse(
        str(request.url_for("truelayer/get-access-token")),
        status_code=302,
    )


@app.get("/truelayer/healthcheck")
async def truelayer_healthcheck(
    truelayer: TrueLayerClient = Depends(get_truelayer_client),
):
    """Check the health of the TrueLayer API."""
    if not truelayer.access_token:
        _LOGGER.warning("TrueLayer access token is not set")
        return JSONResponse(
            status_code=503,
            content={"error": "TrueLayer API access token is not set"},
        )

    response = await truelayer.get_accounts()
    if response.status_code != 200:
        _LOGGER.error(
            "TrueLayer API health check failed with status code %s",
            response.status_code,
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "TrueLayer API is not healthy",
                "status_code": response.status_code,
            },
        )

    return {"status": "OK"}


@app.get("/import/stream")
async def import_stream(
    request: Request,
    truelayer: TrueLayerClient = Depends(get_truelayer_client),
    firefly: FireflyClient = Depends(FireflyClient),
) -> StreamingResponse:
    """Stream the import process."""
    _LOGGER.info("Starting import process")

    importer = Import2Firefly(truelayer, firefly)

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate events for the import process."""
        try:
            async for event in importer.start_import():
                if isinstance(event, dict) and event.get("type") == "progress":
                    yield f"event: progress\ndata: {json.dumps(event['data'])}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            _LOGGER.error(f"Error during import: {e}")
            yield f"data: Error: {e}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/reset-configuration")
async def reset_configuration(request: Request):
    """Reset the configuration."""
    config.reset()
    _LOGGER.info("Configuration reset successfully.")
    return RedirectResponse(str(request.url_for("index")), status_code=302)


app.add_exception_handler(
    TrueLayer2FireflyAuthorizationError, truelayer_authorization_error_handler
)
app.add_exception_handler(
    TrueLayer2FireflyConnectionError, truelayer_connection_error_handler
)
app.add_exception_handler(
    TrueLayer2FireflyTimeoutError, truelayer_timeout_error_handler
)
app.add_exception_handler(TrueLayer2FireflyError, truelayer_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)
