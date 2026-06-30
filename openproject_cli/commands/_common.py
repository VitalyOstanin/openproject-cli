"""Shared Click options and helpers reused across resource subcommands.

The global connection/output options (``--url``, ``--token`` and friends) are
attached both to the top-level group and to every leaf command, so a global
option may be given either before the resource or after the subcommand. The
group records the values it saw into ``ctx.obj``; :func:`resolve_globals` then
merges those defaults with any value the leaf command parsed, with the leaf
winning. The merged :class:`GlobalOptions` doubles as the argument object passed
to ``runtime.client_from_args`` / ``runtime.config_from_args``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import click
from click.core import ParameterSource

from openproject_cli.output import emit, silence_broken_pipe

# A Click option/decorator that wraps a command callback.
Decorator = Callable[[Callable[..., Any]], Callable[..., Any]]


@dataclass(slots=True)
class GlobalOptions:
    """Effective global options after merging the group and leaf levels."""

    url: str | None = None
    token: str | None = None
    config: str | None = None
    timeout: float | None = None
    retries: int | None = None
    insecure: bool | None = None
    human: bool = False


# The shared options, in display order. ``--insecure`` / ``--human`` default to
# None so an unset flag is distinguishable from one explicitly given as the leaf
# override (resolved via the parameter source, not the value).
_OPTION_TABLE: tuple[tuple[str, Decorator], ...] = (
    ("url", click.option("--url", help="OpenProject base URL (overrides config file and OPENPROJECT_URL)")),
    ("token", click.option("--token", help="API token (overrides config file and OPENPROJECT_TOKEN)")),
    (
        "config",
        click.option(
            "--config", help="path to the config file (default: ~/.config/openproject-cli/config.yaml)"
        ),
    ),
    ("timeout", click.option("--timeout", type=float, help="request timeout in seconds (default: 30)")),
    (
        "retries",
        click.option(
            "--retries", type=int, help="retries for idempotent requests on 429/5xx (default: 3, 0 disables)"
        ),
    ),
    (
        "insecure",
        click.option("--insecure", is_flag=True, default=None, help="do not verify TLS certificates"),
    ),
    (
        "human",
        click.option(
            "--human",
            is_flag=True,
            default=None,
            help="human-readable text output instead of the default JSON",
        ),
    ),
)

# Option names shared by the group and every leaf command, derived from the
# single option table above. The attribute names match those read by
# ``runtime.config_from_args``.
GLOBAL_PARAMS = tuple(name for name, _ in _OPTION_TABLE)


def common_options(*exclude: str) -> Decorator:
    """Attach the shared global options, skipping any named in ``exclude``.

    ``auth login`` excludes ``url``/``token`` because it declares its own with
    login-specific help; the merge in :func:`resolve_globals` still picks them
    up by name.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        for name, option in reversed(_OPTION_TABLE):
            if name not in exclude:
                func = option(func)
        return func

    return decorator


def _commandline_globals(ctx: click.Context) -> dict[str, Any]:
    """Return the global params this context actually parsed from the command line."""
    return {
        name: ctx.params[name]
        for name in GLOBAL_PARAMS
        if ctx.get_parameter_source(name) is ParameterSource.COMMANDLINE
    }


def init_globals(ctx: click.Context) -> None:
    """Record the group-level global options into ``ctx.obj`` for leaves to inherit."""
    opts = GlobalOptions()
    for name, value in _commandline_globals(ctx).items():
        setattr(opts, name, value)
    ctx.obj = opts


def resolve_globals(ctx: click.Context) -> GlobalOptions:
    """Merge the group-level globals (``ctx.obj``) with this leaf's overrides."""
    base = ctx.obj if isinstance(ctx.obj, GlobalOptions) else GlobalOptions()
    merged = replace(base)
    for name, value in _commandline_globals(ctx).items():
        setattr(merged, name, value)
    return merged


def paging_options(func: Callable[..., Any]) -> Callable[..., Any]:
    func = click.option("--limit", type=int, default=None, help="page size (default: server default)")(func)
    func = click.option("--offset", type=int, default=1, help="1-based page offset (default: 1)")(func)
    return func


def raw_option(func: Callable[..., Any]) -> Callable[..., Any]:
    return click.option("--raw", is_flag=True, help="output the raw API payload without field normalization")(
        func
    )


def paging_params(offset: int, limit: int | None) -> dict[str, str]:
    params: dict[str, str] = {"offset": str(offset)}
    if limit is not None:
        params["pageSize"] = str(limit)
    return params


def emit_result(result: Any, gopts: GlobalOptions) -> None:
    """Emit a command result honouring the effective ``--human``; skip ``None``."""
    if result is None:
        return
    try:
        emit(result, human=gopts.human)
    except BrokenPipeError:
        silence_broken_pipe()
