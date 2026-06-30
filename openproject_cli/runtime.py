"""Bridge between parsed CLI arguments and an authenticated API client."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from openproject_cli.client import Client
from openproject_cli.config import Config, resolve_config


class GlobalArgs(Protocol):
    """Structural type for the resolved global options the helpers below read.

    Both the Click ``GlobalOptions`` object and any test double satisfy it.
    """

    url: str | None
    token: str | None
    timeout: float | None
    retries: int | None
    insecure: bool | None
    config: str | None


def config_from_args(args: GlobalArgs) -> Config:
    return resolve_config(
        url=args.url,
        token=args.token,
        timeout=args.timeout,
        retries=args.retries,
        insecure=args.insecure,
        config_path=Path(args.config).expanduser() if args.config else None,
    )


def client_from_args(args: GlobalArgs) -> Client:
    """Build a validated API client from global CLI options."""
    return Client(config_from_args(args))
