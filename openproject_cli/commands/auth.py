"""Credential management (``auth``), modelled on ``gh auth``.

- ``auth login``  stores the host URL and API token. With no ``--token`` /
  ``--with-token`` it runs interactively like ``gh``: it opens the OpenProject
  API token page in a browser and prompts for the token to paste. The URL is
  saved to the config file, so ``--url`` only has to be given once (afterwards it
  is reused from the config / ``$OPENPROJECT_URL``). The token goes into the
  system keyring by default; ``--insecure-storage`` writes it to the config file
  instead, and the tool falls back to the file automatically when no keyring
  backend is available.
- ``auth status`` reports the resolved configuration and the token source, and
  verifies the credentials unless ``--offline``.
- ``auth token``  prints the resolved token (like ``gh auth token``).
- ``auth logout`` removes the stored token.
"""

from __future__ import annotations

import getpass
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

import click

from openproject_cli import secrets
from openproject_cli.client import Client
from openproject_cli.commands._common import GlobalOptions, common_options, emit_result, resolve_globals
from openproject_cli.config import (
    DEFAULT_TIMEOUT,
    Config,
    default_config_path,
    load_config_file,
    save_config_file,
)
from openproject_cli.errors import AuthError, InputError, OpenProjectCliError
from openproject_cli.output import silence_broken_pipe
from openproject_cli.runtime import config_from_args

ENV_TOKEN = "OPENPROJECT_TOKEN"

# OpenProject account page where a user generates a personal API token
# (My account -> Access tokens -> API).
ACCESS_TOKEN_PATH = "/my/access_token"


def _config_path(config: str | None) -> Path:
    return Path(config).expanduser() if config else default_config_path()


def _resolve_login_url(gopts: GlobalOptions) -> str:
    if gopts.url:
        return gopts.url.rstrip("/")
    # Reuse a previously configured URL (config file or $OPENPROJECT_URL) so the
    # base URL only needs to be supplied once.
    configured = config_from_args(gopts).base_url
    if configured:
        return configured
    raise InputError("No URL given and none configured. Pass --url <base-url> once.")


def _open_browser(url: str) -> bool:
    try:
        return webbrowser.open(url, new=2)
    except Exception:
        return False


def _prompt_token(url: str, *, no_browser: bool) -> str:
    token_url = url + ACCESS_TOKEN_PATH
    if not sys.stdin.isatty():
        raise InputError(
            "No token provided and the session is not interactive. Use --token <value> "
            f"or --with-token (stdin), or generate one at {token_url}."
        )
    if not no_browser and _open_browser(token_url):
        print(f"Opened {token_url} in your browser.", file=sys.stderr)
    else:
        print(f"Generate an API token at: {token_url}", file=sys.stderr)
    print(
        "There: My account -> Access tokens -> API -> '+ API token', then copy it.",
        file=sys.stderr,
    )
    # getpass reads from the controlling terminal and does not echo the secret,
    # and writes its prompt to stderr so stdout stays clean for JSON output.
    token = getpass.getpass("Paste your API token: ").strip()
    if not token:
        raise InputError("No token entered.")
    return token


def _resolve_token(gopts: GlobalOptions, url: str, *, with_token: bool, no_browser: bool) -> str:
    if with_token:
        token = sys.stdin.readline().strip()
        if not token:
            raise InputError("No token received on stdin for --with-token.")
        return token
    if gopts.token:
        return gopts.token
    return _prompt_token(url, no_browser=no_browser)


def _token_source(gopts: GlobalOptions, config: Config) -> str:
    if os.environ.get(ENV_TOKEN):
        return "env"
    if config.base_url and secrets.get_token(config.base_url):
        return "keyring"
    if load_config_file(_config_path(gopts.config)).get("token"):
        return "file"
    return "none"


@click.group("auth", short_help="manage credentials (login, status, token, logout)")
def auth() -> None:
    """Store and inspect the OpenProject host URL and API token, like 'gh auth'."""


@auth.command(
    "login",
    short_help="authenticate and store the host URL and API token",
    epilog=(
        "\b\n"
        "Examples:\n"
        "  openproject-cli auth login --url https://op.example.com\n"
        "  openproject-cli auth login --url https://op.example.com --with-token < token.txt"
    ),
)
@click.option(
    "--url",
    help="OpenProject base URL (saved to config; reused from config/$OPENPROJECT_URL if omitted)",
)
@click.option("--with-token", "with_token", is_flag=True, help="read the token from stdin")
@click.option("--token", help="API token value (consider --with-token to avoid shell history)")
@click.option(
    "--no-browser",
    "no_browser",
    is_flag=True,
    help="do not open the API token page in a browser during interactive login",
)
@click.option(
    "--insecure-storage",
    "insecure_storage",
    is_flag=True,
    help="store the token in the config file instead of the system keyring",
)
@common_options("url", "token")
@click.pass_context
def login(
    ctx: click.Context, with_token: bool, no_browser: bool, insecure_storage: bool, **_globals: object
) -> None:
    """Store credentials, interactively when no token flag is given.

    With no token flag it opens the API token page in a browser and prompts for
    the token. The token is saved in the system keyring by default; use
    --insecure-storage for the config file.
    """
    gopts = resolve_globals(ctx)
    url = _resolve_login_url(gopts)
    token = _resolve_token(gopts, url, with_token=with_token, no_browser=no_browser)
    path = _config_path(gopts.config)

    # Preserve any existing non-secret settings in the file.
    existing = load_config_file(path)
    timeout = float(existing.get("timeout", DEFAULT_TIMEOUT))
    verify_ssl = bool(existing.get("verify_ssl", True))

    storage = "file"
    if not insecure_storage and secrets.set_token(url, token):
        storage = "keyring"
    elif not insecure_storage:
        print("warning: no keyring backend available; storing token in the config file", file=sys.stderr)

    # With keyring storage the file must not hold the secret.
    file_token = "" if storage == "keyring" else token
    saved = save_config_file(
        Config(base_url=url, token=file_token, timeout=timeout, verify_ssl=verify_ssl), path
    )
    emit_result({"saved": str(saved), "url": url, "tokenStorage": storage}, gopts)


@auth.command("status", short_help="show the resolved configuration and verify it")
@click.option("--offline", is_flag=True, help="do not contact the server")
@common_options()
@click.pass_context
def status(ctx: click.Context, offline: bool, **_globals: object) -> None:
    """Report the effective configuration and token source; verify against the server unless --offline."""
    gopts = resolve_globals(ctx)
    config = config_from_args(gopts)
    result: dict[str, Any] = {
        "configFile": str(_config_path(gopts.config)),
        "url": config.base_url or None,
        "tokenConfigured": bool(config.token),
        "tokenSource": _token_source(gopts, config),
        "verifySsl": config.verify_ssl,
    }
    if offline:
        emit_result(result, gopts)
        return
    if not config.base_url or not config.token:
        result["loggedIn"] = False
        result["error"] = "missing url or token"
        emit_result(result, gopts)
        return
    try:
        user = Client(config).current_user()
        result["loggedIn"] = True
        result["user"] = user.get("name")
        result["userId"] = user.get("id")
    except OpenProjectCliError as exc:
        result["loggedIn"] = False
        result["error"] = str(exc)
    emit_result(result, gopts)


@auth.command("token", short_help="print the resolved API token")
@common_options()
@click.pass_context
def token(ctx: click.Context, **_globals: object) -> None:
    """Print the resolved API token to stdout."""
    gopts = resolve_globals(ctx)
    config = config_from_args(gopts)
    if not config.token:
        raise AuthError("No token configured. Run 'openproject-cli auth login'.")
    # Print the raw token (like 'gh auth token') so it can be captured directly.
    try:
        print(config.token)
    except BrokenPipeError:
        silence_broken_pipe()


@auth.command("logout", short_help="remove the stored token")
@common_options()
@click.pass_context
def logout(ctx: click.Context, **_globals: object) -> None:
    """Remove the stored token from the keyring and the config file."""
    gopts = resolve_globals(ctx)
    config = config_from_args(gopts)
    url = config.base_url
    if not url:
        raise AuthError("No configured URL to log out from.")
    keyring_cleared = secrets.delete_token(url)
    # Drop the token from the config file as well, keeping non-secret settings.
    path = _config_path(gopts.config)
    existing = load_config_file(path)
    file_had_token = bool(existing.get("token"))
    if file_had_token:
        save_config_file(
            Config(
                base_url=existing.get("url", url),
                token="",
                timeout=float(existing.get("timeout", DEFAULT_TIMEOUT)),
                verify_ssl=bool(existing.get("verify_ssl", True)),
            ),
            path,
        )
    emit_result(
        {"loggedOut": url, "keyringCleared": keyring_cleared, "fileTokenCleared": file_had_token}, gopts
    )
