"""Rendering of command results to stdout.

The default format is JSON (stable and machine-readable for non-interactive
use). ``--human`` switches to a flat, dependency-free text rendering: a mapping
becomes ``key: value`` lines and a list of mappings becomes one tab-separated
row per item. Nested structures fall back to compact JSON inside the cell.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO


def emit(data: Any, *, human: bool = False, stream: TextIO | None = None) -> None:
    """Write ``data`` to ``stream`` (stdout) as JSON or human-readable text."""
    out = sys.stdout if stream is None else stream
    if human:
        out.write(to_human(data))
    else:
        out.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))
    out.write("\n")


def to_human(data: Any) -> str:
    if isinstance(data, list):
        return _format_list(data)
    if isinstance(data, dict):
        return _format_mapping(data)
    return _scalar(data)


def _format_list(items: list[Any]) -> str:
    if not items:
        return "(no results)"
    if all(isinstance(item, dict) for item in items):
        # Union of keys, preserving first-seen order, gives a stable column set.
        columns: list[str] = []
        for item in items:
            for key in item:
                if key not in columns:
                    columns.append(key)
        lines = ["\t".join(columns)]
        for item in items:
            lines.append("\t".join(_scalar(item.get(col)) for col in columns))
        return "\n".join(lines)
    return "\n".join(_scalar(item) for item in items)


def _format_mapping(mapping: dict[str, Any]) -> str:
    width = max((len(str(k)) for k in mapping), default=0)
    return "\n".join(f"{str(k) + ':':<{width + 1}} {_scalar(v)}" for k, v in mapping.items())


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
