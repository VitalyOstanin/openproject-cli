"""Shared test fixtures: in-memory API client backed by httpx.MockTransport."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from openproject_cli.client import Client
from openproject_cli.config import Config


def json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


class Router:
    """Routes mock requests by ``(METHOD, path)`` and records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}

    def add(self, method: str, path: str, response: object, status: int = 200) -> Router:
        self._routes[(method.upper(), path)] = lambda _req: json_response(response, status)
        return self

    def add_handler(
        self, method: str, path: str, handler: Callable[[httpx.Request], httpx.Response]
    ) -> Router:
        self._routes[(method.upper(), path)] = handler
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self._routes.get((request.method, request.url.path))
        if handler is None:
            return json_response({"message": f"no mock for {request.method} {request.url.path}"}, 404)
        return handler(request)

    def last(self) -> httpx.Request:
        return self.requests[-1]

    def body(self) -> dict:
        return json.loads(self.last().content)


def make_client(router: Router) -> Client:
    config = Config(base_url="https://op.test", token="TKN")
    return Client(config, transport=httpx.MockTransport(router))


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch) -> dict[str, str]:
    """Replace the keyring backend with an in-memory store for hermetic tests."""
    store: dict[str, str] = {}
    monkeypatch.setattr("openproject_cli.secrets.get_token", lambda url: store.get(url))
    monkeypatch.setattr(
        "openproject_cli.secrets.set_token",
        lambda url, token: bool(store.__setitem__(url, token)) or True,
    )
    monkeypatch.setattr(
        "openproject_cli.secrets.delete_token",
        lambda url: store.pop(url, None) is not None,
    )
    return store


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def cli_run(monkeypatch, router, capsys):
    """Run cli.main with the API client replaced by a MockTransport-backed one.

    Returns a callable ``run(argv) -> (exit_code, stdout, stderr)``; the same
    ``router`` fixture records the requests the command made.
    """
    from openproject_cli import cli, runtime

    client = make_client(router)
    monkeypatch.setattr(runtime, "client_from_args", lambda args: client)

    def run(argv: list[str]) -> tuple[int, str, str]:
        code = cli.main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run
