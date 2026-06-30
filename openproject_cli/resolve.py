"""Resolve human-friendly references (names, identifiers) to numeric API ids.

Every resolver accepts a reference that is either already a numeric id (returned
verbatim) or a name/identifier matched case-insensitively against the relevant
collection. Ambiguous or missing names raise ApiError so the caller fails fast
instead of silently filtering on the wrong id.
"""

from __future__ import annotations

from openproject_cli.client import Client, single_match


def project_id(client: Client, ref: str) -> str:
    """Resolve a project id or identifier. ``/projects/{ref}`` accepts both."""
    ref = ref.strip()
    payload = client.get_json(f"projects/{ref}")
    return str(payload["id"])


def _resolve_by_name(client: Client, path: str, ref: str, kind: str) -> str:
    ref = ref.strip()
    if ref.isdigit():
        return ref
    elements = client.collect(path)
    matches = [str(item["id"]) for item in elements if (item.get("name") or "").casefold() == ref.casefold()]
    names = ", ".join(sorted(str(item.get("name")) for item in elements))
    return single_match(
        matches,
        not_found=f"{kind} {ref!r} was not found. Available: {names}",
        ambiguous=f"{kind} {ref!r} is ambiguous. Pass a numeric id.",
    )


def status_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "statuses", ref, "Status")


def type_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "types", ref, "Type")


def activity_id(client: Client, ref: str) -> str:
    return _resolve_by_name(client, "time_entries/activities", ref, "Activity")
