# TODO

Findings from a multi-reviewer audit (2026-06-30). Severity in brackets.
Detailed per-area reports live in the gitignored `docs/reviews/` directory.

## Contents

- [Critical](#critical)
- [Major](#major)
- [Minor](#minor)
- [Documentation](#documentation)
- [Verified non-issues](#verified-non-issues)

## Critical

- [x] **[CI install]** Switched to `uv venv` + `uv pip install -e ".[dev]"` and
  run tools via `uv run` (`.github/workflows/ci.yml`). Confirmed green on a real
  run (28478223332, success) after the previous run failed.
- [x] **[pytest invocation]** Added `pythonpath = ["."]` to the pytest config; a
  bare `pytest` now runs (86 passed) without `python -m`.
- [x] **[test timeout]** Added `pytest-timeout` with `--timeout=60` in addopts and
  `timeout-minutes: 15` on the CI job.

## Major

- [x] **[comment create — real bug]** Fixed: `comment create` now posts to
  `work_packages/{id}/activities` with `{comment: {raw: ...}}` (confirmed against
  the server source v17.4.0). Test updated.
- [x] **[release tag]** Done (2026-07-01): tagged `v0.1.0`, which ran the publish
  workflow (test→build→publish→release, all green). Published to PyPI via trusted
  publishing (`openproject-cli` 0.1.0, wheel + sdist) and created the GitHub
  Release with both artifacts.
- [x] **[CI action versions]** All GitHub Actions pinned by commit SHA with a
  version comment (checkout v7.0.0, setup-uv v8.2.0, upload-artifact v7.0.1,
  download-artifact v8.0.1, gh-action-pypi-publish v1.14.0). Dependabot/Renovate
  for SHA bumps is still worth adding later.
- [x] **[retry/backoff]** Added bounded retry with exponential backoff and
  `Retry-After` for idempotent methods on 429/5xx; configurable via `--retries` /
  `OPENPROJECT_RETRIES` (default 3, 0 disables); POST never retried.
- [x] **[global options placement]** Done via the Click migration: global options
  (`--url`/`--token`/`--config`/`--timeout`/`--retries`/`--insecure`/`--human`)
  are attached to the group and every leaf, so they work before the resource or
  after the subcommand (a later value overrides an earlier one). See ADR 0002.

## Minor

- [x] **[publish safety]** `publish.yml` now has a test job (lint/format/type/
  tests) that build depends on, a tag↔version check before build, and a final
  `release` job that creates a GitHub Release with the artifacts.
- [x] **[security hardening]** `Client._url` now refuses an absolute URL whose
  host differs from the configured one (blocks token exfiltration), and the
  client warns on stderr when the base URL is plaintext `http://`.
- [x] **[SIGTERM cleanup]** `main()` installs a SIGTERM handler that raises
  `SystemExit`, so `download_to_path`'s `BaseException` cleanup removes the temp
  `.part` file on termination.
- [x] **[timeout literal]** `auth.py` now uses `DEFAULT_TIMEOUT` instead of the
  duplicated `30.0` literal.
- [x] **[config-file timeout]** A bad `timeout` (and `retries`) from the config
  file is now wrapped in `ConfigError`, matching the env-var path.
- [x] **[name resolution paging]** Added `Client.collect()`, which walks all
  collection pages; `resolve.py` and `resolve_principal_id` use it, so a name past
  the first page is now found.
- [x] **[client typing]** The `client` parameter is annotated `Client` across the
  command helpers (done in the Click migration).
- [x] **[chunk size]** Extracted `DEFAULT_CHUNK_SIZE` in `client.py`, used by both
  streaming signatures.
- [x] **[coverage]** CI runs `pytest --cov --cov-report=term-missing
  --cov-fail-under=75` (current coverage ~79%).
- [x] **[setuptools floor]** Bumped `build-system requires` to `setuptools>=77`
  for the PEP 639 string `license` form.
- [x] **[assignee/principal name resolution]** Done: `resolve_principal_id` now
  probes the server with the longest token and narrows client-side to principals
  whose name contains *every* whitespace-separated token (so "Ann Lee" matches
  "Ann Marie Lee"); an exact full-name match wins, and multiple matches raise with
  the candidates listed (`id: name`).
- [x] **[saved query command]** Done: `wp query <id>` wraps `GET
  /api/v3/queries/{id}` and emits `_embedded.results._embedded.elements` through the
  same normalization as `wp list` (`--offset`/`--limit` page, `--raw` unnormalized).

## Documentation

- [x] Added status badges to `README.md` (CI, PyPI version, Python versions,
  license).
- [x] Documented env vars (`OPENPROJECT_TIMEOUT`, `OPENPROJECT_RETRIES`,
  `OPENPROJECT_INSECURE`, `OPENPROJECT_URL`, `OPENPROJECT_CONFIG`) in a README
  table, plus the retries and transport-safety behaviour.
- [x] README "Development" now lists `ruff format --check .`.
- [x] README notes that `--max-bytes`/sha256/atomic write apply only to file
  downloads (not the `-` stdout stream); documented `auth status --offline`.

## Verified non-issues

- Filter names are correct. A reviewer flagged `status_id`/`project_id` (wp) and
  `spentOn`/`workPackage` (time) as wrong, but a live read-only probe against the
  server (v17.4.0) shows every name the CLI sends is accepted (the server tolerates
  both alias forms; an unknown name returns "filter does not exist"). No change
  needed.
- Shell completion is intentionally out of scope; do not add it.
- Token does not leak into diagnostics (no logging; token only printed by the
  explicit `auth token`; input via getpass). If a `--verbose` mode is added, exclude
  the `Authorization` header.
