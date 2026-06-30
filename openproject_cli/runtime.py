"""Bridge between parsed CLI arguments and an authenticated API client."""

from __future__ import annotations

import argparse
from pathlib import Path

from openproject_cli.client import Client
from openproject_cli.config import Config, resolve_config


def config_from_args(args: argparse.Namespace) -> Config:
    return resolve_config(
        url=args.url,
        token=args.token,
        timeout=args.timeout,
        retries=args.retries,
        insecure=args.insecure,
        config_path=Path(args.config).expanduser() if args.config else None,
    )


def client_from_args(args: argparse.Namespace) -> Client:
    """Build a validated API client from global CLI options."""
    return Client(config_from_args(args))
