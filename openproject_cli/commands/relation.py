"""CRUDL for work-package relations (``relation``)."""

from __future__ import annotations

import json
from typing import Any

import click

from openproject_cli import normalize, runtime
from openproject_cli.client import API_PREFIX
from openproject_cli.commands._common import (
    common_options,
    emit_result,
    paging_options,
    paging_params,
    raw_option,
    resolve_globals,
)

RELATION_TYPES = (
    "relates",
    "duplicates",
    "duplicated",
    "blocks",
    "blocked",
    "precedes",
    "follows",
    "includes",
    "partof",
    "requires",
    "required",
)


@click.group("relation", short_help="work-package relations: list, get, create, update, delete")
def relation() -> None:
    """Create, read, update, delete and list relations between work packages."""


@relation.command(
    "list",
    short_help="list relations of a work package",
    epilog="Example: openproject-cli relation list --work-package 1234 --type follows",
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@click.option("--type", "type_", type=click.Choice(RELATION_TYPES), help="filter by relation type")
@paging_options
@raw_option
@common_options()
@click.pass_context
def relation_list(
    ctx: click.Context,
    work_package: int,
    type_: str | None,
    offset: int,
    limit: int | None,
    raw: bool,
    **_globals: object,
) -> None:
    """List relations of a work package, optionally filtered by type."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    params = paging_params(offset, limit)
    if type_:
        params["filters"] = json.dumps([{"type": {"operator": "=", "values": [type_]}}])
    payload = client.get_json(f"work_packages/{work_package}/relations", params=params)
    elements = normalize.collection(payload)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([normalize.relation(item) for item in elements], gopts)


@relation.command("get", short_help="show a single relation")
@click.argument("relation_id", type=int, metavar="ID")
@raw_option
@common_options()
@click.pass_context
def relation_get(ctx: click.Context, relation_id: int, raw: bool, **_globals: object) -> None:
    """Show one relation by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"relations/{relation_id}")
    emit_result(payload if raw else normalize.relation(payload), gopts)


@relation.command(
    "create",
    short_help="create a relation between two work packages",
    epilog="Example: openproject-cli relation create --work-package 1234 --to 5678 --type follows",
)
@click.option("--work-package", "work_package", type=int, required=True, help="source work package id")
@click.option("--to", type=int, required=True, help="target work package id")
@click.option("--type", "type_", type=click.Choice(RELATION_TYPES), required=True, help="relation type")
@click.option("--description", help="optional relation description")
@raw_option
@common_options()
@click.pass_context
def relation_create(
    ctx: click.Context,
    work_package: int,
    to: int,
    type_: str,
    description: str | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Relate a work package (--work-package) to another (--to) with a given type."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    body: dict[str, Any] = {
        "type": type_,
        "_links": {"to": {"href": f"{API_PREFIX}/work_packages/{to}"}},
    }
    if description is not None:
        body["description"] = description
    payload = client.request("POST", f"work_packages/{work_package}/relations", json_body=body).json()
    emit_result(payload if raw else normalize.relation(payload), gopts)


@relation.command("update", short_help="update a relation")
@click.argument("relation_id", type=int, metavar="ID")
@click.option("--type", "type_", type=click.Choice(RELATION_TYPES), help="new relation type")
@click.option("--description", help="new relation description")
@raw_option
@common_options()
@click.pass_context
def relation_update(
    ctx: click.Context,
    relation_id: int,
    type_: str | None,
    description: str | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Update a relation's type or description."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    current = client.get_json(f"relations/{relation_id}")
    body: dict[str, Any] = {}
    if current.get("lockVersion") is not None:
        body["lockVersion"] = current["lockVersion"]
    if type_ is not None:
        body["type"] = type_
    if description is not None:
        body["description"] = description
    payload = client.request("PATCH", f"relations/{relation_id}", json_body=body).json()
    emit_result(payload if raw else normalize.relation(payload), gopts)


@relation.command("delete", short_help="delete a relation")
@click.argument("relation_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def relation_delete(ctx: click.Context, relation_id: int, **_globals: object) -> None:
    """Delete a relation by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.delete(f"relations/{relation_id}")
    emit_result({"deleted": relation_id}, gopts)
