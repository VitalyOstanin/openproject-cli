"""Reduce verbose HAL ``application/json`` payloads to compact, flat dicts.

OpenProject responses embed a large ``_links`` / ``_embedded`` structure. For
day-to-day CLI use the interesting fields are a handful of scalars plus the
title of each linked resource, so these helpers project the raw payload onto a
small dict. The raw response is always reachable via the ``api`` command.
"""

from __future__ import annotations

from typing import Any

from openproject_cli.duration import iso8601_to_hours


def link_title(payload: dict[str, Any], name: str) -> str | None:
    return ((payload.get("_links") or {}).get(name) or {}).get("title")


def link_id(payload: dict[str, Any], name: str) -> int | None:
    href = ((payload.get("_links") or {}).get(name) or {}).get("href")
    if not isinstance(href, str):
        return None
    tail = href.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _text(value: Any) -> str | None:
    """Extract the readable text from a formattable (``{raw, html, ...}``) field."""
    if isinstance(value, dict):
        return value.get("raw")
    return value


def _details(value: Any) -> list[str] | None:
    """Extract the field-change descriptions of an activity (``details[].raw``)."""
    if not isinstance(value, list):
        return None
    texts = [t for item in value if isinstance(item, dict) and (t := _text(item))]
    return texts or None


def work_package(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "subject": payload.get("subject"),
        "type": link_title(payload, "type"),
        "status": link_title(payload, "status"),
        "priority": link_title(payload, "priority"),
        "project": link_title(payload, "project"),
        "projectId": link_id(payload, "project"),
        "author": link_title(payload, "author"),
        "assignee": link_title(payload, "assignee"),
        "percentageDone": payload.get("percentageDone"),
        "startDate": payload.get("startDate"),
        "dueDate": payload.get("dueDate"),
        "createdAt": payload.get("createdAt"),
        "updatedAt": payload.get("updatedAt"),
        "lockVersion": payload.get("lockVersion"),
        "description": _text(payload.get("description")),
    }


def time_entry(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "hours": iso8601_to_hours(payload.get("hours")),
        "spentOn": payload.get("spentOn"),
        "comment": _text(payload.get("comment")),
        "user": link_title(payload, "user"),
        "userId": link_id(payload, "user"),
        "workPackage": link_title(payload, "workPackage"),
        "workPackageId": link_id(payload, "workPackage"),
        "project": link_title(payload, "project"),
        "activity": link_title(payload, "activity"),
        "createdAt": payload.get("createdAt"),
        "updatedAt": payload.get("updatedAt"),
    }


def notification(payload: dict[str, Any]) -> dict[str, Any]:
    activity = (payload.get("_links") or {}).get("activity") or {}
    return {
        "id": payload.get("id"),
        "reason": payload.get("reason"),
        "read": bool(payload.get("readIAN")),
        "wpId": link_id(payload, "resource"),
        "wpTitle": link_title(payload, "resource"),
        "project": link_title(payload, "project"),
        "actor": link_title(payload, "actor"),
        "activityHref": activity.get("href"),
        "createdAt": payload.get("createdAt"),
    }


def comment(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "type": payload.get("_type"),
        "comment": _text(payload.get("comment")),
        "details": _details(payload.get("details")),
        "user": link_title(payload, "user"),
        "userId": link_id(payload, "user"),
        "createdAt": payload.get("createdAt"),
        "version": payload.get("version"),
    }


def attachment(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "fileName": payload.get("fileName"),
        "fileSize": payload.get("fileSize"),
        "contentType": payload.get("contentType"),
        "description": _text(payload.get("description")),
        "author": link_title(payload, "author"),
        "createdAt": payload.get("createdAt"),
        "downloadUrl": ((payload.get("_links") or {}).get("downloadLocation") or {}).get("href"),
    }


def relation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "type": payload.get("type"),
        "reverseType": payload.get("reverseType"),
        "description": payload.get("description"),
        "from": link_id(payload, "from"),
        "to": link_id(payload, "to"),
        "lockVersion": payload.get("lockVersion"),
    }


def collection(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the embedded elements list of a HAL collection response."""
    return (payload.get("_embedded") or {}).get("elements") or []
