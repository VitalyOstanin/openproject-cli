# Contributing

Thanks for considering a contribution.

## Development setup

```sh
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
```

## Before opening a pull request

Run the full check suite and make sure it is green:

```sh
ruff check .
ruff format --check .
pyright
pytest
```

## Guidelines

- Keep the HTTP layer (`client.py`) thin; request shaping belongs in the
  `commands/` modules.
- Tests use `httpx.MockTransport` — no live server is required, and tests must
  not contain real hostnames, tokens, project names or personal data.
- Output stays machine-friendly: JSON on stdout, diagnostics on stderr.
- Add a `## [Unreleased]` entry to `CHANGELOG.md` for user-visible changes.
