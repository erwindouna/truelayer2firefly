""""TrueLayer2Firefly exceptions module."""

class TrueLayer2FireflyError(Exception):
    """Base class for all exceptions raised by TrueLayer2Firefly."""

class TrueLayer2FireflyConnectionError(TrueLayer2FireflyError):
    """Exception raised for connection errors."""

class TrueLayer2FireflyAuthorizationError(TrueLayer2FireflyError):
    """Exception raised for authorization errors."""

class TrueLayer2FireflyTimeoutError(TrueLayer2FireflyError):
    """Exception raised for timeout errors."""

class TrueLayer2FireflyBadRequestError(TrueLayer2FireflyError):
    """Exception raised for bad request errors."""

class TrueLayer2FireflyTimeoutError(TrueLayer2FireflyError):
    """Exception raised for timeout errors."""