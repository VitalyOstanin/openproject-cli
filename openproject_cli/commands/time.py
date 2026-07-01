"""CRUDL for time entries (``time``).

The ``list`` filters are sent to the API (``filters`` query parameter) rather
than applied to a single fetched page, so a date/user/work-package query returns
all matching entries instead of only those on the first page of the unfiltered
collection.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import click

from openproject_cli import normalize, resolve, runtime
from openproject_cli.client import API_PREFIX, Client
from openproject_cli.commands._common import (
    common_options,
    emit_result,
    paging_options,
    paging_params,
    raw_option,
    resolve_globals,
)
from openproject_cli.duration import hours_to_iso8601


def _apply_fields(
    client: Client,
    body: dict[str, Any],
    *,
    hours: float | None = None,
    spent_on: str | None = None,
    comment: str | None = None,
    activity: str | None = None,
) -> None:
    links: dict[str, Any] = body.setdefault("_links", {})
    if hours is not None:
        body["hours"] = hours_to_iso8601(hours)
    if spent_on is not None:
        body["spentOn"] = spent_on
    if comment is not None:
        body["comment"] = {"raw": comment}
    if activity:
        links["activity"] = {
            "href": f"{API_PREFIX}/time_entries/activities/{resolve.activity_id(client, activity)}"
        }
    if not links:
        body.pop("_links")


@click.group("time", short_help="time entries: list, get, create, update, delete")
def time_group() -> None:
    """Create, read, update, delete and list time entries (work logged on tasks)."""


@time_group.command(
    "list",
    short_help="list time entries with server-side filters",
    epilog="Example: openproject-cli time list --user me --since 2026-06-22",
)
@click.option("--user", help="user: 'me', a numeric user id, or a full/partial user name")
@click.option("--project", help="project id or identifier")
@click.option("--work-package", "work_package", type=int, help="work package id")
@click.option("--since", help="earliest spentOn date, inclusive (YYYY-MM-DD)")
@click.option("--until", help="latest spentOn date, inclusive (YYYY-MM-DD)")
@paging_options
@raw_option
@common_options()
@click.pass_context
def time_list(
    ctx: click.Context,
    user: str | None,
    project: str | None,
    work_package: int | None,
    since: str | None,
    until: str | None,
    offset: int,
    limit: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """List time entries. Filters (user, project, work package, date range) are applied by the API."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    filters: list[dict[str, Any]] = []
    if project:
        filters.append({"project": {"operator": "=", "values": [resolve.project_id(client, project)]}})
    if work_package:
        filters.append({"workPackage": {"operator": "=", "values": [str(work_package)]}})
    if user:
        filters.append({"user": {"operator": "=", "values": [client.resolve_principal_id(user)]}})
    if since or until:
        # "<>d" (between dates) accepts an empty bound for an open-ended range.
        filters.append({"spentOn": {"operator": "<>d", "values": [since or "", until or ""]}})
    params = paging_params(offset, limit)
    if filters:
        params["filters"] = json.dumps(filters)
    payload = client.get_json("time_entries", params=params)
    elements = normalize.collection(payload)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([normalize.time_entry(item) for item in elements], gopts)


@time_group.command("get", short_help="show a single time entry")
@click.argument("entry_id", type=int, metavar="ID")
@raw_option
@common_options()
@click.pass_context
def time_get(ctx: click.Context, entry_id: int, raw: bool, **_globals: object) -> None:
    """Show one time entry by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"time_entries/{entry_id}")
    emit_result(payload if raw else normalize.time_entry(payload), gopts)


@time_group.command(
    "create",
    short_help="log time on a work package",
    epilog='Example: openproject-cli time create --work-package 1234 --hours 1.5 --comment "review"',
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@click.option("--hours", type=float, required=True, help="decimal hours, e.g. 1.5")
@click.option("--spent-on", "spent_on", help="date worked (YYYY-MM-DD, default: today)")
@click.option("--comment", help="comment describing the work")
@click.option("--activity", help="activity name or id")
@raw_option
@common_options()
@click.pass_context
def time_create(
    ctx: click.Context,
    work_package: int,
    hours: float,
    spent_on: str | None,
    comment: str | None,
    activity: str | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Create a time entry. --work-package and --hours are required; --spent-on defaults to today."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    body: dict[str, Any] = {
        "hours": hours_to_iso8601(hours),
        "spentOn": spent_on or date.today().isoformat(),
        "_links": {"workPackage": {"href": f"{API_PREFIX}/work_packages/{work_package}"}},
    }
    if comment is not None:
        body["comment"] = {"raw": comment}
    if activity:
        body["_links"]["activity"] = {
            "href": f"{API_PREFIX}/time_entries/activities/{resolve.activity_id(client, activity)}"
        }
    payload = client.request("POST", "time_entries", json_body=body).json()
    emit_result(payload if raw else normalize.time_entry(payload), gopts)


@time_group.command("update", short_help="update a time entry")
@click.argument("entry_id", type=int, metavar="ID")
@click.option("--hours", type=float, help="decimal hours, e.g. 1.5")
@click.option("--spent-on", "spent_on", help="date worked (YYYY-MM-DD)")
@click.option("--comment", help="comment describing the work")
@click.option("--activity", help="activity name or id")
@raw_option
@common_options()
@click.pass_context
def time_update(
    ctx: click.Context,
    entry_id: int,
    hours: float | None,
    spent_on: str | None,
    comment: str | None,
    activity: str | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Update a time entry. The lockVersion is fetched automatically."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    current = client.get_json(f"time_entries/{entry_id}")
    body: dict[str, Any] = {"lockVersion": current.get("lockVersion")}
    _apply_fields(client, body, hours=hours, spent_on=spent_on, comment=comment, activity=activity)
    payload = client.request("PATCH", f"time_entries/{entry_id}", json_body=body).json()
    emit_result(payload if raw else normalize.time_entry(payload), gopts)


@time_group.command("delete", short_help="delete a time entry")
@click.argument("entry_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def time_delete(ctx: click.Context, entry_id: int, **_globals: object) -> None:
    """Delete a time entry by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.delete(f"time_entries/{entry_id}")
    emit_result({"deleted": entry_id}, gopts)
