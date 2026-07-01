"""Command-line entry point for openproject-cli.

Usage: ``openproject-cli [global options] <resource> <action> [options]``.

Global connection and output options are accepted both before the resource and
after the subcommand: a value given after the subcommand overrides the one given
before it. Output is JSON by default; pass ``--human`` for a flat text rendering.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from types import FrameType

import click

from openproject_cli import __version__
from openproject_cli.commands._common import common_options, init_globals
from openproject_cli.commands.api import api
from openproject_cli.commands.attachment import attachment
from openproject_cli.commands.auth import auth
from openproject_cli.commands.comment import comment
from openproject_cli.commands.notification import notification_group
from openproject_cli.commands.relation import relation
from openproject_cli.commands.time import time_group
from openproject_cli.commands.work_packages import wp
from openproject_cli.errors import OpenProjectCliError
from openproject_cli.output import silence_broken_pipe

# Conventional shell exit code for a process terminated by an interrupt.
EXIT_INTERRUPTED = 130
# Env var that re-raises an unexpected exception (full traceback) instead of the
# one-line summary, for debugging.
ENV_DEBUG = "OPENPROJECT_DEBUG"

_DESCRIPTION = "A non-interactive command-line client for the OpenProject API."
_EPILOG = (
    "\b\n"
    "Global options may be given before the resource or after the subcommand, e.g.:\n"
    "  openproject-cli --human wp list --assignee me\n"
    "  openproject-cli wp list --assignee me --human\n"
    "  openproject-cli api GET users/me --url https://op.example.com --token T\n\n"
    "Run 'openproject-cli <resource> --help' or "
    "'openproject-cli <resource> <action> --help' for detailed help."
)


@click.group(
    name="openproject-cli",
    help=_DESCRIPTION,
    epilog=_EPILOG,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@common_options()
@click.version_option(__version__, "--version", message="openproject-cli %(version)s")
@click.pass_context
def cli(ctx: click.Context, **_globals: object) -> None:
    # Record the group-level global options so leaf commands inherit them as
    # defaults (a value repeated after the subcommand overrides these).
    init_globals(ctx)


for _command in (wp, comment, attachment, relation, time_group, notification_group, api, auth):
    cli.add_command(_command)


def _raise_system_exit(signum: int, _frame: FrameType | None) -> None:
    # Turn SIGTERM into SystemExit so context managers and the streaming
    # download's temp-file cleanup (which run on BaseException) execute before
    # the process exits. SIGINT already raises KeyboardInterrupt.
    raise SystemExit(128 + signum)


def _install_signal_handlers() -> None:
    with contextlib.suppress(ValueError):
        signal.signal(signal.SIGTERM, _raise_system_exit)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code (never calls sys.exit itself)."""
    _install_signal_handlers()
    try:
        # standalone_mode=False makes Click return instead of exiting and
        # re-raise ClickException/Abort so we can map them to our exit codes.
        exit_code = cli.main(args=argv, prog_name="openproject-cli", standalone_mode=False)
    except OpenProjectCliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except click.exceptions.Abort:
        # Click converts SIGINT / EOF (e.g. during a prompt) into Abort.
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except click.ClickException as exc:
        # Usage errors carry exit_code 2; other Click errors carry 1.
        exc.show()
        return exc.exit_code
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. ``| head``); exit quietly.
        silence_broken_pipe()
        return 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — top-level guard for any unexpected error
        # An unexpected (non-domain) error: print a one-line summary instead of a
        # raw traceback. Set OPENPROJECT_DEBUG=1 to re-raise the full traceback.
        if os.environ.get(ENV_DEBUG):
            raise
        print(f"error: unexpected failure: {exc}", file=sys.stderr)
        print(f"set {ENV_DEBUG}=1 for a full traceback", file=sys.stderr)
        return 1
    # ``--help`` / ``--version`` make Click return their exit code (0); a normal
    # command returns None after emitting its own output.
    return exit_code if isinstance(exit_code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
