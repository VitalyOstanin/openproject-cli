"""Create, read and update work-package comments (``comment``).

OpenProject exposes comments as work-package *activities*. The API supports
listing, reading and editing them, and creating new comments, but has no
endpoint to delete a comment, so this resource has no ``delete`` action.
"""

from __future__ import annotations

import argparse
from typing import Any

from openproject_cli import normalize, runtime
from openproject_cli.commands._args import add_paging, add_raw, paging_params


def cmd_list(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"work_packages/{args.work_package}/activities", params=paging_params(args))
    elements = normalize.collection(payload)
    if args.comments_only:
        elements = [item for item in elements if (item.get("comment") or {}).get("raw")]
    if args.raw:
        return elements
    return [_resolved_comment(client, item) for item in elements]


def _resolved_comment(client, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize an activity and fill in the author name from its id if missing.

    OpenProject omits the title on the activity user link, so the readable
    author name is otherwise empty even though the id is present.
    """
    result = normalize.comment(payload)
    if result.get("user") is None and result.get("userId") is not None:
        result["user"] = client.user_name(result["userId"])
    return result


def cmd_get(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"activities/{args.id}")
    return payload if args.raw else _resolved_comment(client, payload)


def cmd_create(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    body = {"comment": {"raw": args.text}}
    payload = client.request("POST", f"work_packages/{args.work_package}/activities", json_body=body).json()
    return payload if args.raw else normalize.comment(payload)


def cmd_update(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    current = client.get_json(f"activities/{args.id}")
    body: dict[str, Any] = {"comment": {"raw": args.text}}
    if current.get("lockVersion") is not None:
        body["lockVersion"] = current["lockVersion"]
    payload = client.request("PATCH", f"activities/{args.id}", json_body=body).json()
    return payload if args.raw else normalize.comment(payload)


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "comment",
        help="work-package comments: list, get, create, update",
        description="List, read, create and edit work-package comments. The API has no comment deletion.",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_list = actions.add_parser(
        "list",
        help="list comments/activities of a work package",
        description=(
            "List the activity stream of a work package (comments and field changes). "
            "Note: the activities endpoint is unpaginated, so --offset/--limit have no "
            "effect here and the full stream is always returned."
        ),
        epilog="Example: openproject-cli comment list --work-package 1234 --comments-only",
    )
    p_list.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    p_list.add_argument(
        "--comments-only",
        action="store_true",
        help="only entries that carry a comment (skip field-change activities)",
    )
    add_paging(p_list)
    add_raw(p_list)
    p_list.set_defaults(func=cmd_list)

    p_get = actions.add_parser(
        "get", help="show a single activity", description="Show one activity/comment by id."
    )
    p_get.add_argument("id", type=int, help="activity id")
    add_raw(p_get)
    p_get.set_defaults(func=cmd_get)

    p_create = actions.add_parser(
        "create",
        help="add a comment to a work package",
        description="Add a comment to a work package.",
        epilog='Example: openproject-cli comment create --work-package 1234 "Done, ready for review"',
    )
    p_create.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    p_create.add_argument("text", help="comment body (plain text / Markdown)")
    add_raw(p_create)
    p_create.set_defaults(func=cmd_create)

    p_update = actions.add_parser(
        "update",
        help="edit an existing comment",
        description="Edit the text of an existing comment/activity.",
    )
    p_update.add_argument("id", type=int, help="activity id")
    p_update.add_argument("text", help="new comment body (plain text / Markdown)")
    add_raw(p_update)
    p_update.set_defaults(func=cmd_update)
