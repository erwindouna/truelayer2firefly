from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from exceptions import (
    TrueLayer2FireflyAuthorizationError,
    TrueLayer2FireflyConnectionError,
    TrueLayer2FireflyError,
    TrueLayer2FireflyTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


async def truelayer_authorization_error_handler(
    request: Request, exc: TrueLayer2FireflyAuthorizationError
):
    _LOGGER.error("Authorization error: %s", str(exc))
    return JSONResponse(
        status_code=401, content={"error": "Unauthorized access", "details": str(exc)}
    )


async def truelayer_connection_error_handler(
    request: Request, exc: TrueLayer2FireflyConnectionError
):
    _LOGGER.error("Connection error: %s", str(exc))
    return JSONResponse(
        status_code=503, content={"error": "Connection error", "details": str(exc)}
    )


async def truelayer_timeout_error_handler(
    request: Request, exc: TrueLayer2FireflyTimeoutError
):
    _LOGGER.error("Timeout error: %s", str(exc))
    return JSONResponse(
        status_code=504, content={"error": "Request timeout", "details": str(exc)}
    )


async def truelayer_error_handler(request: Request, exc: TrueLayer2FireflyError):
    _LOGGER.error("TrueLayer error: %s", str(exc))
    return JSONResponse(
        status_code=500, content={"error": "TrueLayer error", "details": str(exc)}
    )


async def generic_exception_handler(request: Request, exc: Exception):
    _LOGGER.exception("Unhandled exception: %s", str(exc))
    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "details": str(exc)}
    )
