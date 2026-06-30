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

import argparse
import getpass
import sys
import webbrowser
from pathlib import Path
from typing import Any

from openproject_cli import secrets
from openproject_cli.client import Client
from openproject_cli.config import (
    Config,
    default_config_path,
    load_config_file,
    save_config_file,
)
from openproject_cli.errors import AuthError, InputError, OpenProjectCliError
from openproject_cli.runtime import config_from_args

ENV_TOKEN = "OPENPROJECT_TOKEN"

# OpenProject account page where a user generates a personal API token
# (My account -> Access tokens -> API).
ACCESS_TOKEN_PATH = "/my/access_token"


def _config_path(args: argparse.Namespace) -> Path:
    return Path(args.config).expanduser() if args.config else default_config_path()


def _resolve_login_url(args: argparse.Namespace) -> str:
    if args.url:
        return args.url.rstrip("/")
    # Reuse a previously configured URL (config file or $OPENPROJECT_URL) so the
    # base URL only needs to be supplied once.
    configured = config_from_args(args).base_url
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


def _resolve_token(args: argparse.Namespace, url: str) -> str:
    if args.with_token:
        token = sys.stdin.readline().strip()
        if not token:
            raise InputError("No token received on stdin for --with-token.")
        return token
    if args.token:
        return args.token
    return _prompt_token(url, no_browser=args.no_browser)


def cmd_login(args: argparse.Namespace) -> Any:
    url = _resolve_login_url(args)
    token = _resolve_token(args, url)
    path = _config_path(args)

    # Preserve any existing non-secret settings in the file.
    existing = load_config_file(path)
    timeout = float(existing.get("timeout", 30.0))
    verify_ssl = bool(existing.get("verify_ssl", True))

    storage = "file"
    if not args.insecure_storage and secrets.set_token(url, token):
        storage = "keyring"
    else:
        if not args.insecure_storage:
            print("warning: no keyring backend available; storing token in the config file", file=sys.stderr)

    # With keyring storage the file must not hold the secret.
    file_token = "" if storage == "keyring" else token
    saved = save_config_file(
        Config(base_url=url, token=file_token, timeout=timeout, verify_ssl=verify_ssl), path
    )
    return {"saved": str(saved), "url": url, "tokenStorage": storage}


def _token_source(args: argparse.Namespace, config: Config) -> str:
    import os

    if os.environ.get(ENV_TOKEN):
        return "env"
    if config.base_url and secrets.get_token(config.base_url):
        return "keyring"
    if load_config_file(_config_path(args)).get("token"):
        return "file"
    return "none"


def cmd_status(args: argparse.Namespace) -> Any:
    config = config_from_args(args)
    result: dict[str, Any] = {
        "configFile": str(_config_path(args)),
        "url": config.base_url or None,
        "tokenConfigured": bool(config.token),
        "tokenSource": _token_source(args, config),
        "verifySsl": config.verify_ssl,
    }
    if args.offline:
        return result
    if not config.base_url or not config.token:
        result["loggedIn"] = False
        result["error"] = "missing url or token"
        return result
    try:
        user = Client(config).current_user()
        result["loggedIn"] = True
        result["user"] = user.get("name")
        result["userId"] = user.get("id")
    except OpenProjectCliError as exc:
        result["loggedIn"] = False
        result["error"] = str(exc)
    return result


def cmd_token(args: argparse.Namespace) -> Any:
    config = config_from_args(args)
    if not config.token:
        raise AuthError("No token configured. Run 'openproject-cli auth login'.")
    # Print the raw token (like 'gh auth token') so it can be captured directly.
    print(config.token)
    return None


def cmd_logout(args: argparse.Namespace) -> Any:
    config = config_from_args(args)
    url = config.base_url
    if not url:
        raise AuthError("No configured URL to log out from.")
    keyring_cleared = secrets.delete_token(url)
    # Drop the token from the config file as well, keeping non-secret settings.
    path = _config_path(args)
    existing = load_config_file(path)
    file_had_token = bool(existing.get("token"))
    if file_had_token:
        save_config_file(
            Config(
                base_url=existing.get("url", url),
                token="",
                timeout=float(existing.get("timeout", 30.0)),
                verify_ssl=bool(existing.get("verify_ssl", True)),
            ),
            path,
        )
    return {"loggedOut": url, "keyringCleared": keyring_cleared, "fileTokenCleared": file_had_token}


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "auth",
        help="manage credentials (login, status, token, logout)",
        description="Store and inspect the OpenProject host URL and API token, like 'gh auth'.",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_login = actions.add_parser(
        "login",
        help="authenticate and store the host URL and API token",
        description=(
            "Store credentials. With no token flag it runs interactively: opens the "
            "API token page in a browser and prompts for the token. The token is saved "
            "in the system keyring by default; use --insecure-storage for the config file."
        ),
        epilog=(
            "Examples:\n"
            "  openproject-cli auth login --url https://op.example.com\n"
            "  openproject-cli auth login --url https://op.example.com --with-token < token.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_login.add_argument(
        "--url",
        help="OpenProject base URL (saved to config; reused from config/$OPENPROJECT_URL if omitted)",
    )
    p_login.add_argument(
        "--with-token", dest="with_token", action="store_true", help="read the token from stdin"
    )
    p_login.add_argument("--token", help="API token value (consider --with-token to avoid shell history)")
    p_login.add_argument(
        "--no-browser",
        dest="no_browser",
        action="store_true",
        help="do not open the API token page in a browser during interactive login",
    )
    p_login.add_argument(
        "--insecure-storage",
        dest="insecure_storage",
        action="store_true",
        help="store the token in the config file instead of the system keyring",
    )
    p_login.set_defaults(func=cmd_login)

    p_status = actions.add_parser(
        "status",
        help="show the resolved configuration and verify it",
        description="Report the effective configuration and token source; verify against the server unless --offline.",
    )
    p_status.add_argument("--offline", action="store_true", help="do not contact the server")
    p_status.set_defaults(func=cmd_status)

    p_token = actions.add_parser(
        "token", help="print the resolved API token", description="Print the resolved API token to stdout."
    )
    p_token.set_defaults(func=cmd_token)

    p_logout = actions.add_parser(
        "logout",
        help="remove the stored token",
        description="Remove the stored token from the keyring and the config file.",
    )
    p_logout.set_defaults(func=cmd_logout)
