"""Exception hierarchy for openproject-cli.

All domain errors derive from OpenProjectCliError so the CLI entry point can
catch them, print a structured message to stderr and exit non-zero, while
unexpected exceptions keep their full traceback.
"""

from __future__ import annotations


class OpenProjectCliError(Exception):
    """Base class for all expected, user-facing errors."""

    #: Process exit code used when this error reaches the CLI entry point.
    exit_code = 1


class ConfigError(OpenProjectCliError):
    """Configuration file or environment is missing or malformed."""

    exit_code = 2


class AuthError(OpenProjectCliError):
    """No usable credentials, or the server rejected them (HTTP 401)."""

    exit_code = 3


class InputError(OpenProjectCliError):
    """Invalid command-line input that the argument parser cannot catch on its own."""

    exit_code = 2


class NotFoundError(OpenProjectCliError):
    """The requested resource does not exist (HTTP 404)."""

    exit_code = 4


class ApiError(OpenProjectCliError):
    """The OpenProject API returned an error response.

    ``status`` is the HTTP status code and ``payload`` is the parsed response
    body (a dict for OpenProject's ``application/hal+json`` errors, otherwise
    the raw text), so callers and tests can inspect the server's own message.
    """

    exit_code = 5

    def __init__(self, status: int, message: str, payload: object | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload
