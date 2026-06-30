"""Thin synchronous HTTP client for the OpenProject API v3.

The client owns transport concerns only: base URL joining, Basic ``apikey``
authentication, JSON (de)serialisation and mapping HTTP error responses to the
exception hierarchy. Request shaping (filters, payloads) lives in the command
modules so this layer stays small and the raw ``api`` passthrough can reuse it.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from openproject_cli.config import Config
from openproject_cli.errors import ApiError, AuthError, InputError, NotFoundError, OpenProjectCliError

API_PREFIX = "/api/v3"
USER_AGENT = "openproject-cli"

# OpenProject names custom fields ``customField<N>`` both as scalar payload keys
# and as ``_links`` entries (for list-valued fields).
_CUSTOM_FIELD_RE = re.compile(r"^customField\d+$")


class Client:
    """Synchronous OpenProject API client backed by ``httpx.Client``."""

    def __init__(self, config: Config, *, transport: httpx.BaseTransport | None = None) -> None:
        config.require_credentials()
        self._config = config
        # Per-process caches: a CLI run is short-lived, so a plain dict (no TTL)
        # is enough to avoid refetching the same schema or user within one run.
        self._schema_name_cache: dict[str, dict[str, str]] = {}
        self._user_name_cache: dict[int, str | None] = {}
        self._http = httpx.Client(
            transport=transport,
            base_url=config.base_url,
            # OpenProject accepts the API token as HTTP Basic with the literal
            # username "apikey"; this bypasses the session CSRF protection that
            # the cookie-based login requires.
            auth=("apikey", config.token),
            timeout=config.timeout,
            verify=config.verify_ssl,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- low-level request -------------------------------------------------

    def _url(self, path: str) -> str:
        """Join a caller-supplied path onto the API, tolerating either form.

        Accepts ``work_packages``, ``/work_packages``, ``api/v3/work_packages``
        or a full ``/api/v3/...`` path so the raw ``api`` command and the
        resource commands can pass whatever is most natural.

        Hrefs returned by the API may carry the deployment sub-path of an
        instance hosted under a prefix (e.g. ``/openproject/api/v3/...``). Any
        path that contains the API prefix is reduced to its api-absolute form
        (``/api/v3/...``) so httpx re-joins it against ``base_url`` exactly once;
        otherwise prepending the prefix again would duplicate it (HTTP 404).
        """
        path = path.strip()
        if path.startswith(("http://", "https://")):
            return path
        if not path.startswith("/"):
            path = "/" + path
        index = path.find(API_PREFIX + "/")
        if index != -1:
            return path[index:]
        if path == API_PREFIX:
            return path
        return API_PREFIX + path

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        files: Any | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request and raise a typed error for non-2xx responses."""
        try:
            response = self._http.request(
                method.upper(),
                self._url(path),
                params=params,
                json=json_body,
                files=files,
                data=data,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiError(0, f"HTTP request to OpenProject failed: {exc}") from exc
        if response.is_success:
            return response
        self._raise_for_status(response)
        return response  # unreachable, keeps type checkers happy

    def _raise_for_status(self, response: httpx.Response) -> None:
        payload: object
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            payload = response.text
        message = _extract_message(payload) or f"HTTP {response.status_code} {response.reason_phrase}"
        if response.status_code == 401:
            raise AuthError(f"Authentication failed (HTTP 401): {message}")
        if response.status_code == 404:
            raise NotFoundError(message)
        raise ApiError(response.status_code, message, payload)

    # -- typed helpers -----------------------------------------------------

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params).json()

    def delete(self, path: str) -> None:
        # OpenProject rejects a DELETE without a Content-Type header (HTTP 406,
        # "Missing content-type header"), even though the request carries no body.
        self.request("DELETE", path, headers={"Content-Type": "application/json"})

    # -- streaming transfers (never buffer a whole file in memory) ----------

    def stream_download(self, path: str, dest: BinaryIO, *, chunk_size: int = 65536) -> int:
        """Stream a response body into ``dest`` chunk by chunk; return byte count.

        Uses ``httpx.stream`` so the payload is written out as it arrives and is
        never accumulated in memory. On an error response the (small) body is
        read to surface the server message.
        """
        written = 0
        try:
            with self._http.stream("GET", self._url(path)) as response:
                if not response.is_success:
                    response.read()
                    self._raise_for_status(response)
                for chunk in response.iter_bytes(chunk_size):
                    dest.write(chunk)
                    written += len(chunk)
        except httpx.HTTPError as exc:
            raise ApiError(0, f"HTTP request to OpenProject failed: {exc}") from exc
        return written

    def download_to_path(
        self,
        path: str,
        dest_path: str,
        *,
        chunk_size: int = 65536,
        max_bytes: int | None = None,
    ) -> dict[str, Any]:
        """Stream a response body to ``dest_path`` via a temp file + atomic rename.

        The content is written to a temporary file in the destination directory
        and renamed into place only after the download fully succeeds. The whole
        file is never held in memory; on any failure (HTTP error, size limit,
        cancellation) the temporary file is removed and an existing destination
        file is left untouched. Returns ``{"bytes": int, "sha256": str}``.
        """
        dest = Path(dest_path)
        digest = hashlib.sha256()
        total = 0
        fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
        tmp = Path(tmp_name)
        try:
            with (
                os.fdopen(fd, "wb") as handle,
                self._http.stream("GET", self._url(path)) as response,
            ):
                if not response.is_success:
                    response.read()
                    self._raise_for_status(response)
                for chunk in response.iter_bytes(chunk_size):
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise InputError(
                            f"Download exceeds the limit of {max_bytes} bytes; "
                            "pass a larger --max-bytes to override."
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            tmp.replace(dest)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise ApiError(0, f"HTTP request to OpenProject failed: {exc}") from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return {"bytes": total, "sha256": digest.hexdigest()}

    def upload_attachment(
        self,
        work_package_id: int,
        file_path: str,
        *,
        file_name: str | None = None,
        description: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file as a work-package attachment, streaming it from disk.

        The open binary file object is handed to httpx, which reads it
        incrementally for the multipart body — the file is never loaded into
        memory in full.
        """
        file_name = file_name or os.path.basename(file_path)
        metadata: dict[str, Any] = {"fileName": file_name}
        if description:
            metadata["description"] = {"raw": description}
        content_type = content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        with open(file_path, "rb") as handle:
            files = {
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file": (file_name, handle, content_type),
            }
            return self.request("POST", f"work_packages/{work_package_id}/attachments", files=files).json()

    # -- resolution helpers (shared by commands) ---------------------------

    def current_user(self) -> dict[str, Any]:
        return self.get_json("users/me")

    def user_name(self, user_id: int) -> str | None:
        """Resolve a user id to a display name (cached per process).

        OpenProject omits the title on some user links (notably activity
        authors), exposing only the id; this fills the gap. A failed lookup
        (deleted/forbidden user) is cached as ``None`` so it is not retried.
        """
        if user_id in self._user_name_cache:
            return self._user_name_cache[user_id]
        try:
            payload = self.get_json(f"users/{user_id}")
        except OpenProjectCliError:
            self._user_name_cache[user_id] = None
            return None
        name = payload.get("name")
        self._user_name_cache[user_id] = name
        return name

    def custom_fields(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract a work package's custom field values with resolved names.

        Returns ``[]`` without any extra request when the payload carries no
        custom field values. Otherwise the field names are read from the work
        package's schema (one request per distinct schema, cached); a field
        whose name cannot be resolved keeps ``name: null`` but its value.
        """
        raw = _extract_raw_custom_fields(payload)
        if not raw:
            return []
        schema_href = ((payload.get("_links") or {}).get("schema") or {}).get("href")
        names = self._custom_field_names(schema_href)
        return [{"key": key, "name": names.get(key), "value": value} for key, value in raw.items()]

    def _custom_field_names(self, schema_href: str | None) -> dict[str, str]:
        if not schema_href:
            return {}
        cached = self._schema_name_cache.get(schema_href)
        if cached is not None:
            return cached
        names: dict[str, str] = {}
        try:
            schema = self.get_json(schema_href)
        except OpenProjectCliError:
            # Degrade to unnamed custom fields when the schema is unreadable.
            self._schema_name_cache[schema_href] = names
            return names
        for key, definition in schema.items():
            if _CUSTOM_FIELD_RE.match(key) and isinstance(definition, dict):
                name = definition.get("name")
                if isinstance(name, str):
                    names[key] = name
        self._schema_name_cache[schema_href] = names
        return names

    def resolve_principal_id(self, ref: str) -> str:
        """Resolve ``me`` / a numeric id / an exact principal name to a user id.

        Mirrors the assignee/user resolution used by the MCP server: ``me`` maps
        to the authenticated user, a digit string is taken as an id verbatim,
        and anything else is matched case-insensitively against principal names
        via ``/principals?filters=...`` — erroring on no match or ambiguity.
        """
        ref = ref.strip()
        if ref.casefold() == "me":
            return str(self.current_user()["id"])
        if ref.isdigit():
            return ref
        filters = json.dumps([{"name": {"operator": "~", "values": [ref]}}])
        payload = self.get_json("principals", params={"filters": filters, "pageSize": "100"})
        elements = payload.get("_embedded", {}).get("elements", [])
        matches = [
            str(item["id"]) for item in elements if (item.get("name") or "").casefold() == ref.casefold()
        ]
        if not matches:
            raise ApiError(404, f"Principal {ref!r} was not found. Pass a numeric user id or 'me'.")
        if len(matches) > 1:
            raise ApiError(
                400, f"Principal {ref!r} is ambiguous ({len(matches)} matches). Pass a numeric id."
            )
        return matches[0]


def _extract_raw_custom_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Collect non-empty ``customField<N>`` values from a work package payload.

    Scalar values come from the top level; list/single linked values come from
    ``_links`` (using the link titles, which are the human-readable choices).
    """
    raw: dict[str, Any] = {}
    for key, value in payload.items():
        if _CUSTOM_FIELD_RE.match(key) and value not in (None, ""):
            raw[key] = value
    for key, link in (payload.get("_links") or {}).items():
        if not _CUSTOM_FIELD_RE.match(key):
            continue
        if isinstance(link, list):
            titles = [t for item in link if isinstance(item, dict) and (t := item.get("title"))]
            if titles:
                raw[key] = titles
        elif isinstance(link, dict) and link.get("title"):
            raw[key] = link["title"]
    return raw


def _extract_message(payload: object) -> str | None:
    """Pull a human-readable message out of an OpenProject error body."""
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            # Append validation details when present (HAL ``_embedded.errors``).
            errors = payload.get("_embedded", {}).get("errors")
            if isinstance(errors, list):
                extra = [str(e["message"]) for e in errors if isinstance(e, dict) and e.get("message")]
                if extra:
                    return message + " " + "; ".join(extra)
            return message
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return None
