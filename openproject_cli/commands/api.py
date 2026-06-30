"""Raw OpenProject API passthrough (``api``), modelled on ``gh api``.

Lets the caller hit any endpoint directly. Fields given with ``-f``/``-F`` become
query parameters for GET/HEAD/DELETE and a JSON body otherwise; ``--input``
sends a JSON body read from a file or stdin.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from openproject_cli import runtime
from openproject_cli.commands._common import common_options, emit_result, resolve_globals
from openproject_cli.errors import InputError

_BODILESS = {"GET", "HEAD", "DELETE"}

_EPILOG = """\
\b
Examples:
  openproject-cli api GET work_packages/1234
  openproject-cli api GET work_packages -f pageSize=5
  openproject-cli api POST time_entries --input body.json
"""


def _parse_fields(raw: tuple[str, ...], *, typed: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in raw:
        key, sep, value = item.partition("=")
        if not sep:
            raise InputError(f"Invalid field {item!r}; expected key=value.")
        if typed:
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        else:
            result[key] = value
    return result


@click.command(
    "api",
    short_help="make a raw authenticated API request to any endpoint",
    epilog=_EPILOG,
)
@click.argument("method")
@click.argument("path")
@click.option("-f", "--field", "field", multiple=True, metavar="KEY=VALUE", help="string field (repeatable)")
@click.option(
    "-F",
    "--raw-field",
    "raw_field",
    multiple=True,
    metavar="KEY=VALUE",
    help="typed field: value parsed as JSON, falling back to string (repeatable)",
)
@click.option("--input", "input_", help="read a JSON request body from a file, or '-' for stdin")
@common_options()
@click.pass_context
def api(
    ctx: click.Context,
    method: str,
    path: str,
    field: tuple[str, ...],
    raw_field: tuple[str, ...],
    input_: str | None,
    **_globals: object,
) -> None:
    """Send an authenticated request to any OpenProject API path.

    The path may be given with or without the /api/v3 prefix.
    """
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    method = method.upper()

    fields: dict[str, Any] = {}
    fields.update(_parse_fields(field, typed=False))
    fields.update(_parse_fields(raw_field, typed=True))

    params: dict[str, Any] | None = None
    body: Any | None = None

    if input_ is not None:
        if input_ == "-":
            text = sys.stdin.read()
        else:
            with open(input_, encoding="utf-8") as handle:
                text = handle.read()
        try:
            body = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"--input is not valid JSON: {exc}") from exc
    elif fields:
        if method in _BODILESS:
            params = fields
        else:
            body = fields

    response = client.request(method, path, params=params, json_body=body)
    if response.status_code == 204 or not response.content:
        emit_result(None, gopts)
        return
    try:
        emit_result(response.json(), gopts)
    except (json.JSONDecodeError, ValueError):
        emit_result(response.text, gopts)
