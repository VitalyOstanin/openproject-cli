"""Read-side access to OpenProject in-app notifications (``notification``)."""

from __future__ import annotations

import json
from typing import Any

import click

from openproject_cli import normalize, runtime
from openproject_cli.commands._common import (
    common_options,
    emit_result,
    paging_options,
    paging_params,
    raw_option,
    resolve_globals,
)

JSON_CONTENT_TYPE = {"Content-Type": "application/json"}


@click.group("notification", short_help="notifications: list, read, unread")
def notification_group() -> None:
    """List in-app notifications and mark them read/unread."""


@notification_group.command("list", short_help="list in-app notifications (newest first)")
@paging_options
@raw_option
@common_options()
@click.pass_context
def notification_list(
    ctx: click.Context, offset: int, limit: int | None, raw: bool, **_globals: object
) -> None:
    """List in-app notifications, most recent first."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    params: dict[str, Any] = paging_params(offset, limit)
    params["sortBy"] = json.dumps([["id", "desc"]])
    payload = client.get_json("notifications", params=params)
    elements = normalize.collection(payload)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([normalize.notification(item) for item in elements], gopts)


@notification_group.command("read", short_help="mark a notification as read")
@click.argument("notification_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def notification_read(ctx: click.Context, notification_id: int, **_globals: object) -> None:
    """Mark a single notification as read."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.request("POST", f"notifications/{notification_id}/read_ian", headers=JSON_CONTENT_TYPE)
    emit_result({"read": notification_id}, gopts)


@notification_group.command("unread", short_help="mark a notification as unread")
@click.argument("notification_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def notification_unread(ctx: click.Context, notification_id: int, **_globals: object) -> None:
    """Mark a single notification as unread."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.request("POST", f"notifications/{notification_id}/unread_ian", headers=JSON_CONTENT_TYPE)
    emit_result({"unread": notification_id}, gopts)
