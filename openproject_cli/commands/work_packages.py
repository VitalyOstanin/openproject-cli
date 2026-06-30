"""CRUDL for work packages (``wp``)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from openproject_cli import normalize, resolve, runtime
from openproject_cli.client import API_PREFIX
from openproject_cli.commands._args import add_paging, add_raw, paging_params


def _href(kind: str, ref: str) -> str:
    return f"{API_PREFIX}/{kind}/{ref}"


def cmd_list(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    filters: list[dict[str, Any]] = []
    if args.project:
        filters.append(
            {"project_id": {"operator": "=", "values": [resolve.project_id(client, args.project)]}}
        )
    if args.status:
        filters.append({"status_id": {"operator": "=", "values": [resolve.status_id(client, args.status)]}})
    if args.open:
        filters.append({"status_id": {"operator": "o", "values": []}})
    if args.type:
        filters.append({"type": {"operator": "=", "values": [resolve.type_id(client, args.type)]}})
    if args.assignee:
        filters.append(
            {"assignee": {"operator": "=", "values": [client.resolve_principal_id(args.assignee)]}}
        )
    if args.subject:
        filters.append({"subject": {"operator": "~", "values": [args.subject]}})
    params = paging_params(args)
    if filters:
        params["filters"] = json.dumps(filters)
    payload = client.get_json("work_packages", params=params)
    elements = normalize.collection(payload)
    if args.raw:
        return elements
    return [_with_custom_fields(client, item) for item in elements]


def _with_custom_fields(client, payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize.work_package(payload)
    result["customFields"] = client.custom_fields(payload)
    return result


def cmd_get(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"work_packages/{args.id}")
    return payload if args.raw else _with_custom_fields(client, payload)


def _build_links_and_body(client, args: argparse.Namespace, *, for_create: bool) -> dict[str, Any]:
    body: dict[str, Any] = {}
    links: dict[str, Any] = {}
    if getattr(args, "subject", None) is not None:
        body["subject"] = args.subject
    if getattr(args, "description", None) is not None:
        body["description"] = {"raw": args.description}
    if getattr(args, "start_date", None) is not None:
        body["startDate"] = args.start_date
    if getattr(args, "due_date", None) is not None:
        body["dueDate"] = args.due_date
    if getattr(args, "done_ratio", None) is not None:
        body["percentageDone"] = args.done_ratio
    if for_create:
        links["project"] = {"href": _href("projects", resolve.project_id(client, args.project))}
        links["type"] = {"href": _href("types", resolve.type_id(client, args.type))}
    if getattr(args, "status", None):
        links["status"] = {"href": _href("statuses", resolve.status_id(client, args.status))}
    if getattr(args, "type", None) and not for_create:
        links["type"] = {"href": _href("types", resolve.type_id(client, args.type))}
    if getattr(args, "assignee", None):
        links["assignee"] = {"href": _href("users", client.resolve_principal_id(args.assignee))}
    if getattr(args, "parent", None):
        links["parent"] = {"href": _href("work_packages", str(args.parent))}
    if links:
        body["_links"] = links
    return body


def cmd_create(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    body = _build_links_and_body(client, args, for_create=True)
    payload = client.request("POST", "work_packages", json_body=body).json()
    return payload if args.raw else normalize.work_package(payload)


def cmd_update(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    body = _build_links_and_body(client, args, for_create=False)
    # PATCH requires the current lockVersion for optimistic locking.
    current = client.get_json(f"work_packages/{args.id}")
    body["lockVersion"] = current.get("lockVersion")
    payload = client.request("PATCH", f"work_packages/{args.id}", json_body=body).json()
    return payload if args.raw else normalize.work_package(payload)


def cmd_delete(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    client.delete(f"work_packages/{args.id}")
    return {"deleted": args.id}


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "wp",
        help="work packages (tasks): list, get, create, update, delete",
        description="Create, read, update, delete and list work packages (tasks).",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_list = actions.add_parser(
        "list",
        help="list/search work packages with filters",
        description="List work packages. Filters are combined with AND and resolved server-side.",
        epilog="Example: openproject-cli wp list --assignee me --open --project my-project",
    )
    p_list.add_argument("--project", help="project id or identifier")
    p_list.add_argument("--status", help="status name or id")
    p_list.add_argument("--type", help="type name or id (e.g. Task, Bug)")
    p_list.add_argument("--assignee", help="assignee: 'me', a numeric user id, or an exact user/group name")
    p_list.add_argument("--subject", help="filter by subject substring")
    p_list.add_argument("--open", action="store_true", help="only open work packages")
    add_paging(p_list)
    add_raw(p_list)
    p_list.set_defaults(func=cmd_list)

    p_get = actions.add_parser(
        "get", help="show a single work package", description="Show one work package by id."
    )
    p_get.add_argument("id", type=int, help="work package id")
    add_raw(p_get)
    p_get.set_defaults(func=cmd_get)

    p_create = actions.add_parser(
        "create",
        help="create a work package",
        description="Create a work package. --project, --type and --subject are required.",
        epilog='Example: openproject-cli wp create --project my-project --type Task --subject "Fix X"',
    )
    p_create.add_argument("--project", required=True, help="project id or identifier")
    p_create.add_argument("--type", required=True, help="type name or id (e.g. Task)")
    p_create.add_argument("--subject", required=True, help="work package subject")
    p_create.add_argument("--description", help="description (plain text / Markdown)")
    p_create.add_argument("--status", help="initial status name or id")
    p_create.add_argument("--assignee", help="assignee: 'me', a user id, or an exact name")
    p_create.add_argument("--parent", type=int, help="parent work package id")
    p_create.add_argument("--start-date", dest="start_date", help="start date (YYYY-MM-DD)")
    p_create.add_argument("--due-date", dest="due_date", help="due date (YYYY-MM-DD)")
    p_create.add_argument("--done-ratio", dest="done_ratio", type=int, help="percentage done (0-100)")
    add_raw(p_create)
    p_create.set_defaults(func=cmd_create)

    p_update = actions.add_parser(
        "update",
        help="update a work package",
        description="Update fields of a work package. The lockVersion is fetched automatically.",
        epilog='Example: openproject-cli wp update 1234 --status "In progress" --done-ratio 50',
    )
    p_update.add_argument("id", type=int, help="work package id")
    p_update.add_argument("--subject", help="new subject")
    p_update.add_argument("--description", help="new description")
    p_update.add_argument("--status", help="new status name or id")
    p_update.add_argument("--type", help="new type name or id")
    p_update.add_argument("--assignee", help="new assignee: 'me', a user id, or an exact name")
    p_update.add_argument("--parent", type=int, help="new parent work package id")
    p_update.add_argument("--start-date", dest="start_date", help="start date (YYYY-MM-DD)")
    p_update.add_argument("--due-date", dest="due_date", help="due date (YYYY-MM-DD)")
    p_update.add_argument("--done-ratio", dest="done_ratio", type=int, help="percentage done (0-100)")
    add_raw(p_update)
    p_update.set_defaults(func=cmd_update)

    p_delete = actions.add_parser(
        "delete", help="delete a work package", description="Delete a work package by id."
    )
    p_delete.add_argument("id", type=int, help="work package id")
    p_delete.set_defaults(func=cmd_delete)
