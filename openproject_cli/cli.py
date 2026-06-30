"""Command-line entry point for openproject-cli.

Usage: ``openproject-cli [global options] <resource> <action> [options]``.

Global connection and output options are accepted before the resource so that
each resource keeps its own option namespace clean. Output is JSON by default;
pass ``--human`` for a flat text rendering.
"""

from __future__ import annotations

import argparse
import sys

from openproject_cli import __version__
from openproject_cli.commands import api, attachment, comment, relation, work_packages
from openproject_cli.commands import auth as auth_cmd
from openproject_cli.commands import time as time_cmd
from openproject_cli.errors import OpenProjectCliError
from openproject_cli.output import emit

_DESCRIPTION = "A non-interactive command-line client for the OpenProject API."
_EPILOG = (
    "Global options go before the resource, e.g.:\n"
    "  openproject-cli --human wp list --assignee me\n"
    "  openproject-cli --url https://op.example.com --token T api GET users/me\n\n"
    "Run 'openproject-cli <resource> --help' or "
    "'openproject-cli <resource> <action> --help' for detailed help."
)


def _silence_broken_pipe() -> None:
    """Redirect stdout to /dev/null so the interpreter shutdown flush is silent."""
    import os

    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openproject-cli",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"openproject-cli {__version__}")
    parser.add_argument("--url", help="OpenProject base URL (overrides config file and OPENPROJECT_URL)")
    parser.add_argument("--token", help="API token (overrides config file and OPENPROJECT_TOKEN)")
    parser.add_argument(
        "--config", help="path to the config file (default: ~/.config/openproject-cli/config.yaml)"
    )
    parser.add_argument("--timeout", type=float, help="request timeout in seconds (default: 30)")
    parser.add_argument(
        "--insecure",
        action="store_const",
        const=True,
        default=None,
        help="do not verify TLS certificates",
    )
    parser.add_argument(
        "--human", action="store_true", help="human-readable text output instead of the default JSON"
    )

    subparsers = parser.add_subparsers(dest="resource", required=True, metavar="<resource>")
    for module in (work_packages, comment, attachment, relation, time_cmd, api, auth_cmd):
        module.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except OpenProjectCliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. ``| head``); exit quietly.
        _silence_broken_pipe()
        return 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    if result is not None:
        emit(result, human=args.human)
    return 0


if __name__ == "__main__":
    sys.exit(main())
