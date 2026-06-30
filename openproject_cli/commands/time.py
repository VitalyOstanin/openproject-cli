"""CRUDL for time entries (``time``).

The ``list`` filters are sent to the API (``filters`` query parameter) rather
than applied to a single fetched page, so a date/user/work-package query returns
all matching entries instead of only those on the first page of the unfiltered
collection.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any

from openproject_cli import normalize, resolve, runtime
from openproject_cli.client import API_PREFIX
from openproject_cli.commands._args import add_paging, add_raw, paging_params
from openproject_cli.duration import hours_to_iso8601


def cmd_list(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    filters: list[dict[str, Any]] = []
    if args.project:
        filters.append({"project": {"operator": "=", "values": [resolve.project_id(client, args.project)]}})
    if args.work_package:
        filters.append({"workPackage": {"operator": "=", "values": [str(args.work_package)]}})
    if args.user:
        filters.append({"user": {"operator": "=", "values": [client.resolve_principal_id(args.user)]}})
    if args.since or args.until:
        # "<>d" (between dates) accepts an empty bound for an open-ended range.
        filters.append({"spentOn": {"operator": "<>d", "values": [args.since or "", args.until or ""]}})
    params = paging_params(args)
    if filters:
        params["filters"] = json.dumps(filters)
    payload = client.get_json("time_entries", params=params)
    elements = normalize.collection(payload)
    if args.raw:
        return elements
    return [normalize.time_entry(item) for item in elements]


def cmd_get(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"time_entries/{args.id}")
    return payload if args.raw else normalize.time_entry(payload)


def _apply_fields(client, args: argparse.Namespace, body: dict[str, Any]) -> None:
    links: dict[str, Any] = body.setdefault("_links", {})
    if getattr(args, "hours", None) is not None:
        body["hours"] = hours_to_iso8601(args.hours)
    if getattr(args, "spent_on", None) is not None:
        body["spentOn"] = args.spent_on
    if getattr(args, "comment", None) is not None:
        body["comment"] = {"raw": args.comment}
    if getattr(args, "activity", None):
        links["activity"] = {
            "href": f"{API_PREFIX}/time_entries/activities/{resolve.activity_id(client, args.activity)}"
        }
    if not links:
        body.pop("_links")


def cmd_create(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    spent_on = args.spent_on or date.today().isoformat()
    body: dict[str, Any] = {
        "hours": hours_to_iso8601(args.hours),
        "spentOn": spent_on,
        "_links": {"workPackage": {"href": f"{API_PREFIX}/work_packages/{args.work_package}"}},
    }
    if args.comment is not None:
        body["comment"] = {"raw": args.comment}
    if args.activity:
        body["_links"]["activity"] = {
            "href": f"{API_PREFIX}/time_entries/activities/{resolve.activity_id(client, args.activity)}"
        }
    payload = client.request("POST", "time_entries", json_body=body).json()
    return payload if args.raw else normalize.time_entry(payload)


def cmd_update(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    current = client.get_json(f"time_entries/{args.id}")
    body: dict[str, Any] = {"lockVersion": current.get("lockVersion")}
    _apply_fields(client, args, body)
    payload = client.request("PATCH", f"time_entries/{args.id}", json_body=body).json()
    return payload if args.raw else normalize.time_entry(payload)


def cmd_delete(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    client.delete(f"time_entries/{args.id}")
    return {"deleted": args.id}


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "time",
        help="time entries: list, get, create, update, delete",
        description="Create, read, update, delete and list time entries (work logged on tasks).",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_list = actions.add_parser(
        "list",
        help="list time entries with server-side filters",
        description="List time entries. Filters (user, project, work package, date range) are applied by the API.",
        epilog="Example: openproject-cli time list --user me --since 2026-06-22",
    )
    p_list.add_argument("--user", help="user: 'me', a numeric user id, or an exact user name")
    p_list.add_argument("--project", help="project id or identifier")
    p_list.add_argument("--work-package", dest="work_package", type=int, help="work package id")
    p_list.add_argument("--since", help="earliest spentOn date, inclusive (YYYY-MM-DD)")
    p_list.add_argument("--until", help="latest spentOn date, inclusive (YYYY-MM-DD)")
    add_paging(p_list)
    add_raw(p_list)
    p_list.set_defaults(func=cmd_list)

    p_get = actions.add_parser(
        "get", help="show a single time entry", description="Show one time entry by id."
    )
    p_get.add_argument("id", type=int, help="time entry id")
    add_raw(p_get)
    p_get.set_defaults(func=cmd_get)

    p_create = actions.add_parser(
        "create",
        help="log time on a work package",
        description="Create a time entry. --work-package and --hours are required; --spent-on defaults to today.",
        epilog='Example: openproject-cli time create --work-package 1234 --hours 1.5 --comment "review"',
    )
    p_create.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    p_create.add_argument("--hours", type=float, required=True, help="decimal hours, e.g. 1.5")
    p_create.add_argument("--spent-on", dest="spent_on", help="date worked (YYYY-MM-DD, default: today)")
    p_create.add_argument("--comment", help="comment describing the work")
    p_create.add_argument("--activity", help="activity name or id")
    add_raw(p_create)
    p_create.set_defaults(func=cmd_create)

    p_update = actions.add_parser(
        "update",
        help="update a time entry",
        description="Update a time entry. The lockVersion is fetched automatically.",
    )
    p_update.add_argument("id", type=int, help="time entry id")
    p_update.add_argument("--hours", type=float, help="decimal hours, e.g. 1.5")
    p_update.add_argument("--spent-on", dest="spent_on", help="date worked (YYYY-MM-DD)")
    p_update.add_argument("--comment", help="comment describing the work")
    p_update.add_argument("--activity", help="activity name or id")
    add_raw(p_update)
    p_update.set_defaults(func=cmd_update)

    p_delete = actions.add_parser(
        "delete", help="delete a time entry", description="Delete a time entry by id."
    )
    p_delete.add_argument("id", type=int, help="time entry id")
    p_delete.set_defaults(func=cmd_delete)
