"""CRUDL for work packages (``wp``)."""

from __future__ import annotations

import json
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


def _href(kind: str, ref: str) -> str:
    return f"{API_PREFIX}/{kind}/{ref}"


def _with_custom_fields(client: Client, payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize.work_package(payload)
    result["customFields"] = client.custom_fields(payload)
    return result


def _build_links_and_body(
    client: Client,
    *,
    for_create: bool,
    subject: str | None = None,
    description: str | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    done_ratio: int | None = None,
    project: str | None = None,
    type_: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    parent: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    links: dict[str, Any] = {}
    if subject is not None:
        body["subject"] = subject
    if description is not None:
        body["description"] = {"raw": description}
    if start_date is not None:
        body["startDate"] = start_date
    if due_date is not None:
        body["dueDate"] = due_date
    if done_ratio is not None:
        body["percentageDone"] = done_ratio
    if for_create:
        links["project"] = {"href": _href("projects", resolve.project_id(client, project or ""))}
        links["type"] = {"href": _href("types", resolve.type_id(client, type_ or ""))}
    if status:
        links["status"] = {"href": _href("statuses", resolve.status_id(client, status))}
    if type_ and not for_create:
        links["type"] = {"href": _href("types", resolve.type_id(client, type_))}
    if assignee:
        links["assignee"] = {"href": _href("users", client.resolve_principal_id(assignee))}
    if parent:
        links["parent"] = {"href": _href("work_packages", str(parent))}
    if links:
        body["_links"] = links
    return body


@click.group("wp", short_help="work packages (tasks): list, get, create, update, delete")
def wp() -> None:
    """Create, read, update, delete and list work packages (tasks)."""


@wp.command(
    "list",
    short_help="list/search work packages with filters",
    epilog="Example: openproject-cli wp list --assignee me --open --project my-project",
)
@click.option("--project", help="project id or identifier")
@click.option("--status", help="status name or id")
@click.option("--type", "type_", help="type name or id (e.g. Task, Bug)")
@click.option("--assignee", help="assignee: 'me', a numeric user id, or a full/partial user/group name")
@click.option("--subject", help="filter by subject substring")
@click.option("--open", "open_", is_flag=True, help="only open work packages")
@paging_options
@raw_option
@common_options()
@click.pass_context
def wp_list(
    ctx: click.Context,
    project: str | None,
    status: str | None,
    type_: str | None,
    assignee: str | None,
    subject: str | None,
    open_: bool,
    offset: int,
    limit: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """List work packages. Filters are combined with AND and resolved server-side."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    filters: list[dict[str, Any]] = []
    if project:
        filters.append({"project_id": {"operator": "=", "values": [resolve.project_id(client, project)]}})
    if status:
        filters.append({"status_id": {"operator": "=", "values": [resolve.status_id(client, status)]}})
    if open_:
        filters.append({"status_id": {"operator": "o", "values": []}})
    if type_:
        filters.append({"type": {"operator": "=", "values": [resolve.type_id(client, type_)]}})
    if assignee:
        filters.append({"assignee": {"operator": "=", "values": [client.resolve_principal_id(assignee)]}})
    if subject:
        filters.append({"subject": {"operator": "~", "values": [subject]}})
    params = paging_params(offset, limit)
    if filters:
        params["filters"] = json.dumps(filters)
    payload = client.get_json("work_packages", params=params)
    elements = normalize.collection(payload)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([_with_custom_fields(client, item) for item in elements], gopts)


@wp.command(
    "query",
    short_help="run a saved query by id and list its work packages",
    epilog="Example: openproject-cli wp query 532",
)
@click.argument("query_id", type=int, metavar="ID")
@paging_options
@raw_option
@common_options()
@click.pass_context
def wp_query(
    ctx: click.Context,
    query_id: int,
    offset: int,
    limit: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Run a saved OpenProject query and list its work packages.

    Fetches ``GET /api/v3/queries/{id}`` (which embeds the executed results) and
    emits the work packages exactly like ``wp list``. ``--offset``/``--limit``
    page the results, overriding the query's own pagination. Use ``api GET
    queries/{id}`` for the full query definition (filters, columns, sort).
    """
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"queries/{query_id}", params=paging_params(offset, limit))
    results = (payload.get("_embedded") or {}).get("results") or {}
    elements = normalize.collection(results)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([_with_custom_fields(client, item) for item in elements], gopts)


@wp.command("get", short_help="show a single work package")
@click.argument("wp_id", type=int, metavar="ID")
@raw_option
@common_options()
@click.pass_context
def wp_get(ctx: click.Context, wp_id: int, raw: bool, **_globals: object) -> None:
    """Show one work package by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"work_packages/{wp_id}")
    emit_result(payload if raw else _with_custom_fields(client, payload), gopts)


@wp.command(
    "create",
    short_help="create a work package",
    epilog='Example: openproject-cli wp create --project my-project --type Task --subject "Fix X"',
)
@click.option("--project", required=True, help="project id or identifier")
@click.option("--type", "type_", required=True, help="type name or id (e.g. Task)")
@click.option("--subject", required=True, help="work package subject")
@click.option("--description", help="description (plain text / Markdown)")
@click.option("--status", help="initial status name or id")
@click.option("--assignee", help="assignee: 'me', a user id, or a full/partial name")
@click.option("--parent", type=int, help="parent work package id")
@click.option("--start-date", "start_date", help="start date (YYYY-MM-DD)")
@click.option("--due-date", "due_date", help="due date (YYYY-MM-DD)")
@click.option("--done-ratio", "done_ratio", type=int, help="percentage done (0-100)")
@raw_option
@common_options()
@click.pass_context
def wp_create(
    ctx: click.Context,
    project: str,
    type_: str,
    subject: str,
    description: str | None,
    status: str | None,
    assignee: str | None,
    parent: int | None,
    start_date: str | None,
    due_date: str | None,
    done_ratio: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Create a work package. --project, --type and --subject are required."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    body = _build_links_and_body(
        client,
        for_create=True,
        subject=subject,
        description=description,
        start_date=start_date,
        due_date=due_date,
        done_ratio=done_ratio,
        project=project,
        type_=type_,
        status=status,
        assignee=assignee,
        parent=parent,
    )
    payload = client.request("POST", "work_packages", json_body=body).json()
    emit_result(payload if raw else normalize.work_package(payload), gopts)


@wp.command(
    "update",
    short_help="update a work package",
    epilog='Example: openproject-cli wp update 1234 --status "In progress" --done-ratio 50',
)
@click.argument("wp_id", type=int, metavar="ID")
@click.option("--subject", help="new subject")
@click.option("--description", help="new description")
@click.option("--status", help="new status name or id")
@click.option("--type", "type_", help="new type name or id")
@click.option("--assignee", help="new assignee: 'me', a user id, or a full/partial name")
@click.option("--parent", type=int, help="new parent work package id")
@click.option("--start-date", "start_date", help="start date (YYYY-MM-DD)")
@click.option("--due-date", "due_date", help="due date (YYYY-MM-DD)")
@click.option("--done-ratio", "done_ratio", type=int, help="percentage done (0-100)")
@raw_option
@common_options()
@click.pass_context
def wp_update(
    ctx: click.Context,
    wp_id: int,
    subject: str | None,
    description: str | None,
    status: str | None,
    type_: str | None,
    assignee: str | None,
    parent: int | None,
    start_date: str | None,
    due_date: str | None,
    done_ratio: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Update fields of a work package. The lockVersion is fetched automatically."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    body = _build_links_and_body(
        client,
        for_create=False,
        subject=subject,
        description=description,
        start_date=start_date,
        due_date=due_date,
        done_ratio=done_ratio,
        type_=type_,
        status=status,
        assignee=assignee,
        parent=parent,
    )
    # PATCH requires the current lockVersion for optimistic locking.
    current = client.get_json(f"work_packages/{wp_id}")
    body["lockVersion"] = current.get("lockVersion")
    payload = client.request("PATCH", f"work_packages/{wp_id}", json_body=body).json()
    emit_result(payload if raw else normalize.work_package(payload), gopts)


@wp.command("delete", short_help="delete a work package")
@click.argument("wp_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def wp_delete(ctx: click.Context, wp_id: int, **_globals: object) -> None:
    """Delete a work package by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.delete(f"work_packages/{wp_id}")
    emit_result({"deleted": wp_id}, gopts)
