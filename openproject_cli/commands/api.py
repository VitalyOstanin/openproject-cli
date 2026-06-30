"""Raw OpenProject API passthrough (``api``), modelled on ``gh api``.

Lets the caller hit any endpoint directly. Fields given with ``-f``/``-F`` become
query parameters for GET/HEAD/DELETE and a JSON body otherwise; ``--input``
sends a JSON body read from a file or stdin.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from openproject_cli import runtime
from openproject_cli.errors import InputError

_BODILESS = {"GET", "HEAD", "DELETE"}


def _parse_fields(raw: list[str] | None, *, typed: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in raw or []:
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


def cmd_api(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    method = args.method.upper()

    fields: dict[str, Any] = {}
    fields.update(_parse_fields(args.field, typed=False))
    fields.update(_parse_fields(args.raw_field, typed=True))

    params: dict[str, Any] | None = None
    body: Any | None = None

    if args.input is not None:
        if args.input == "-":
            text = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
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

    response = client.request(method, args.path, params=params, json_body=body)
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "api",
        help="make a raw authenticated API request to any endpoint",
        description=(
            "Send an authenticated request to any OpenProject API path. "
            "The path may be given with or without the /api/v3 prefix."
        ),
        epilog=(
            "Examples:\n"
            "  openproject-cli api GET work_packages/1234\n"
            "  openproject-cli api GET work_packages -f pageSize=5\n"
            "  openproject-cli api POST time_entries --input body.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("method", help="HTTP method (GET, POST, PATCH, DELETE, ...)")
    parser.add_argument("path", help="API path, e.g. work_packages/1234")
    parser.add_argument(
        "-f", "--field", action="append", metavar="KEY=VALUE", help="string field (repeatable)"
    )
    parser.add_argument(
        "-F",
        "--raw-field",
        dest="raw_field",
        action="append",
        metavar="KEY=VALUE",
        help="typed field: value parsed as JSON, falling back to string (repeatable)",
    )
    parser.add_argument("--input", help="read a JSON request body from a file, or '-' for stdin")
    parser.set_defaults(func=cmd_api)
