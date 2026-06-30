"""Create, read and update work-package comments (``comment``).

OpenProject exposes comments as work-package *activities*. The API supports
listing, reading and editing them, and creating new comments, but has no
endpoint to delete a comment, so this resource has no ``delete`` action.
"""

from __future__ import annotations

from typing import Any

import click

from openproject_cli import normalize, runtime
from openproject_cli.client import Client
from openproject_cli.commands._common import (
    common_options,
    emit_result,
    paging_options,
    paging_params,
    raw_option,
    resolve_globals,
)


def _resolved_comment(client: Client, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize an activity and fill in the author name from its id if missing.

    OpenProject omits the title on the activity user link, so the readable
    author name is otherwise empty even though the id is present.
    """
    result = normalize.comment(payload)
    if result.get("user") is None and result.get("userId") is not None:
        result["user"] = client.user_name(result["userId"])
    return result


@click.group("comment", short_help="work-package comments: list, get, create, update")
def comment() -> None:
    """List, read, create and edit work-package comments. The API has no comment deletion."""


@comment.command(
    "list",
    short_help="list comments/activities of a work package",
    epilog="Example: openproject-cli comment list --work-package 1234 --comments-only",
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@click.option(
    "--comments-only",
    "comments_only",
    is_flag=True,
    help="only entries that carry a comment (skip field-change activities)",
)
@paging_options
@raw_option
@common_options()
@click.pass_context
def comment_list(
    ctx: click.Context,
    work_package: int,
    comments_only: bool,
    offset: int,
    limit: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """List the activity stream of a work package (comments and field changes).

    Note: the activities endpoint is unpaginated, so --offset/--limit have no
    effect here and the full stream is always returned.
    """
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"work_packages/{work_package}/activities", params=paging_params(offset, limit))
    elements = normalize.collection(payload)
    if comments_only:
        elements = [item for item in elements if (item.get("comment") or {}).get("raw")]
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([_resolved_comment(client, item) for item in elements], gopts)


@comment.command("get", short_help="show a single activity")
@click.argument("activity_id", type=int, metavar="ID")
@raw_option
@common_options()
@click.pass_context
def comment_get(ctx: click.Context, activity_id: int, raw: bool, **_globals: object) -> None:
    """Show one activity/comment by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"activities/{activity_id}")
    emit_result(payload if raw else _resolved_comment(client, payload), gopts)


@comment.command(
    "create",
    short_help="add a comment to a work package",
    epilog='Example: openproject-cli comment create --work-package 1234 "Done, ready for review"',
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@click.argument("text")
@raw_option
@common_options()
@click.pass_context
def comment_create(ctx: click.Context, work_package: int, text: str, raw: bool, **_globals: object) -> None:
    """Add a comment to a work package."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    body = {"comment": {"raw": text}}
    payload = client.request("POST", f"work_packages/{work_package}/activities", json_body=body).json()
    emit_result(payload if raw else normalize.comment(payload), gopts)


@comment.command("update", short_help="edit an existing comment")
@click.argument("activity_id", type=int, metavar="ID")
@click.argument("text")
@raw_option
@common_options()
@click.pass_context
def comment_update(ctx: click.Context, activity_id: int, text: str, raw: bool, **_globals: object) -> None:
    """Edit the text of an existing comment/activity."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    current = client.get_json(f"activities/{activity_id}")
    body: dict[str, Any] = {"comment": {"raw": text}}
    if current.get("lockVersion") is not None:
        body["lockVersion"] = current["lockVersion"]
    payload = client.request("PATCH", f"activities/{activity_id}", json_body=body).json()
    emit_result(payload if raw else normalize.comment(payload), gopts)
