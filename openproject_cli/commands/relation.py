"""CRUDL for work-package relations (``relation``)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from openproject_cli import normalize, runtime
from openproject_cli.client import API_PREFIX
from openproject_cli.commands._args import add_paging, add_raw, paging_params

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


def cmd_list(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    params = paging_params(args)
    if args.type:
        params["filters"] = json.dumps([{"type": {"operator": "=", "values": [args.type]}}])
    payload = client.get_json(f"work_packages/{args.work_package}/relations", params=params)
    elements = normalize.collection(payload)
    if args.raw:
        return elements
    return [normalize.relation(item) for item in elements]


def cmd_get(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"relations/{args.id}")
    return payload if args.raw else normalize.relation(payload)


def cmd_create(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    body: dict[str, Any] = {
        "type": args.type,
        "_links": {"to": {"href": f"{API_PREFIX}/work_packages/{args.to}"}},
    }
    if args.description is not None:
        body["description"] = args.description
    payload = client.request("POST", f"work_packages/{args.work_package}/relations", json_body=body).json()
    return payload if args.raw else normalize.relation(payload)


def cmd_update(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    current = client.get_json(f"relations/{args.id}")
    body: dict[str, Any] = {}
    if current.get("lockVersion") is not None:
        body["lockVersion"] = current["lockVersion"]
    if args.type is not None:
        body["type"] = args.type
    if args.description is not None:
        body["description"] = args.description
    payload = client.request("PATCH", f"relations/{args.id}", json_body=body).json()
    return payload if args.raw else normalize.relation(payload)


def cmd_delete(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    client.delete(f"relations/{args.id}")
    return {"deleted": args.id}


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "relation",
        help="work-package relations: list, get, create, update, delete",
        description="Create, read, update, delete and list relations between work packages.",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_list = actions.add_parser(
        "list",
        help="list relations of a work package",
        description="List relations of a work package, optionally filtered by type.",
        epilog="Example: openproject-cli relation list --work-package 1234 --type follows",
    )
    p_list.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    p_list.add_argument("--type", choices=RELATION_TYPES, help="filter by relation type")
    add_paging(p_list)
    add_raw(p_list)
    p_list.set_defaults(func=cmd_list)

    p_get = actions.add_parser("get", help="show a single relation", description="Show one relation by id.")
    p_get.add_argument("id", type=int, help="relation id")
    add_raw(p_get)
    p_get.set_defaults(func=cmd_get)

    p_create = actions.add_parser(
        "create",
        help="create a relation between two work packages",
        description="Relate a work package (--work-package) to another (--to) with a given type.",
        epilog="Example: openproject-cli relation create --work-package 1234 --to 5678 --type follows",
    )
    p_create.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="source work package id"
    )
    p_create.add_argument("--to", type=int, required=True, help="target work package id")
    p_create.add_argument("--type", choices=RELATION_TYPES, required=True, help="relation type")
    p_create.add_argument("--description", help="optional relation description")
    add_raw(p_create)
    p_create.set_defaults(func=cmd_create)

    p_update = actions.add_parser(
        "update", help="update a relation", description="Update a relation's type or description."
    )
    p_update.add_argument("id", type=int, help="relation id")
    p_update.add_argument("--type", choices=RELATION_TYPES, help="new relation type")
    p_update.add_argument("--description", help="new relation description")
    add_raw(p_update)
    p_update.set_defaults(func=cmd_update)

    p_delete = actions.add_parser("delete", help="delete a relation", description="Delete a relation by id.")
    p_delete.add_argument("id", type=int, help="relation id")
    p_delete.set_defaults(func=cmd_delete)
