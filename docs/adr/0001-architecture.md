# 1. Thin client with per-resource commands and JSON-first output

Date: 2026-06-30

## Status

Superseded by [ADR-0002](0002-cli-framework-click.md) (argument parsing moved
from `argparse` to Click). The rest of this record still stands.

## Context

The tool is a non-interactive command-line client for the OpenProject API v3,
meant to be driven by scripts and AI agents rather than used as an interactive
terminal UI. It needs predictable output, full endpoint coverage, and room to
grow command by command.

## Decision

- **Layering.** A thin synchronous HTTP client (`client.py`) owns only transport
  concerns: base-URL joining, Basic `apikey` authentication, JSON
  (de)serialisation and mapping HTTP errors to a typed exception hierarchy.
  Request shaping (filters, request bodies) lives in one module per resource
  under `commands/`. The same client backs the raw `api` passthrough.
- **No TUI dependencies.** Argument parsing uses the standard library
  `argparse`; there is no `click`/`rich` dependency. Runtime dependencies are
  limited to `httpx` and `pyyaml`.
- **JSON-first output.** Commands return plain data structures that the entry
  point serialises as JSON by default; `--human` selects a flat text rendering
  and `--raw` returns the unmodified API payload.
- **Server-side filtering.** List commands translate their options into the
  API's `filters` parameter so the server returns exactly the matching set,
  instead of fetching one page and filtering in the client.
- **Streaming transfers.** Attachment download and upload stream through the
  HTTP layer and never buffer a whole file in memory.
- **Credentials like `gh`.** The token is stored in the OS keyring by default,
  keyed by host URL; `--insecure-storage` (or the absence of a keyring backend)
  writes it to the YAML config file instead. The config file always holds the
  non-secret settings (URL, timeout, TLS verification). Resolution order for the
  token is flag, environment variable, keyring, config file.

## Consequences

- Adding a resource or action is local: a new `commands/` module (or action) and
  its tests, with no changes to the transport layer.
- Tests run entirely against `httpx.MockTransport`; no live server is needed.
- The raw `api` command guarantees coverage of endpoints that have no dedicated
  command yet.
- Human-readable output is intentionally minimal; consumers that need rich
  formatting post-process the JSON.
