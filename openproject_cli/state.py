"""Local persistent state for openproject-cli.

Currently holds the set of work-package ids ever seen assigned to a given user
on a given host, so ``wp list --include-past`` can surface tasks the user was
assigned to previously (OpenProject offers no server-side "was assigned" filter).
Keyed by ``(base_url, user id)``. The file is best-effort: a missing or corrupt
file degrades to an empty history rather than failing the command.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

ENV_STATE = "OPENPROJECT_STATE"


def default_state_path() -> Path:
    """Return the state file path, honouring OPENPROJECT_STATE / XDG_STATE_HOME."""
    override = os.environ.get(ENV_STATE)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "openproject-cli" / "assignee-history.json"


def _key(base_url: str, uid: int | str) -> str:
    return f"{base_url}#{uid}"


def _read_all(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_assignee_history(base_url: str, uid: int | str, path: Path | None = None) -> list[int]:
    """Return the sorted list of work-package ids ever assigned to ``uid``."""
    path = path or default_state_path()
    value = _read_all(path).get(_key(base_url, uid))
    if not isinstance(value, list):
        return []
    ids = {int(v) for v in value if isinstance(v, (int, str)) and str(v).lstrip("-").isdigit()}
    return sorted(ids)


def save_assignee_history(
    base_url: str, uid: int | str, ids: Iterable[int], path: Path | None = None
) -> Path:
    """Persist the id set for ``(base_url, uid)``, merging into the existing file."""
    path = path or default_state_path()
    data = _read_all(path)
    data[_key(base_url, uid)] = sorted({int(i) for i in ids})
    # Best-effort: a failure to persist the auxiliary history must never break the
    # primary command (an unwritable state dir or a full disk should be tolerated).
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(path.parent, 0o700)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    except OSError:
        pass
    return path
