"""Resolve human-friendly references (names, identifiers) to numeric API ids.

Every resolver accepts a reference that is either already a numeric id (returned
verbatim) or a name/identifier matched case-insensitively against the relevant
collection. Ambiguous or missing names raise ApiError so the caller fails fast
instead of silently filtering on the wrong id.
"""

from __future__ import annotations

from openproject_cli.client import Client
from openproject_cli.errors import ApiError
from openproject_cli.normalize import collection


def project_id(client: Client, ref: str) -> str:
    """Resolve a project id or identifier. ``/projects/{ref}`` accepts both."""
    ref = ref.strip()
    payload = client.get_json(f"projects/{ref}")
    return str(payload["id"])


def _resolve_by_name(client: Client, path: str, ref: str, kind: str) -> str:
    ref = ref.strip()
    if ref.isdigit():
        return ref
    elements = collection(client.get_json(path, params={"pageSize": "200"}))
    matches = [str(item["id"]) for item in elements if (item.get("name") or "").casefold() == ref.casefold()]
    if not matches:
        names = ", ".join(sorted(str(item.get("name")) for item in elements))
        raise ApiError(404, f"{kind} {ref!r} was not found. Available: {names}")
    if len(matches) > 1:
        raise ApiError(400, f"{kind} {ref!r} is ambiguous. Pass a numeric id.")
    return matches[0]


def status_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "statuses", ref, "Status")


def type_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "types", ref, "Type")


def activity_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "time_entries/activities", ref, "Activity")
