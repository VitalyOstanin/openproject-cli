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
  run tools via `uv run` (`.github/workflows/ci.yml`). Verify the next CI run is
  green (the externally-managed failure is fixed locally but only a real run
  confirms it end to end).
- [x] **[pytest invocation]** Added `pythonpath = ["."]` to the pytest config; a
  bare `pytest` now runs (86 passed) without `python -m`.
- [x] **[test timeout]** Added `pytest-timeout` with `--timeout=60` in addopts and
  `timeout-minutes: 15` on the CI job.

## Major

- [x] **[comment create — real bug]** Fixed: `comment create` now posts to
  `work_packages/{id}/activities` with `{comment: {raw: ...}}` (confirmed against
  the server source v17.4.0). Test updated.
- [ ] **[release tag]** Deferred by decision: do not create the `v0.1.0` tag yet
  (tagging triggers a real PyPI publish). Tag separately once PyPI publishing
  (trusted publishing / token) and the package name are confirmed. The
  publish-workflow gate below is done.
- [x] **[CI action versions]** All GitHub Actions pinned by commit SHA with a
  version comment (checkout v7.0.0, setup-uv v8.2.0, upload-artifact v7.0.1,
  download-artifact v8.0.1, gh-action-pypi-publish v1.14.0). Dependabot/Renovate
  for SHA bumps is still worth adding later.
- [x] **[retry/backoff]** Added bounded retry with exponential backoff and
  `Retry-After` for idempotent methods on 429/5xx; configurable via `--retries` /
  `OPENPROJECT_RETRIES` (default 3, 0 disables); POST never retried.
- [ ] **[global options placement]** Global options (`--human`, `--url`, `--token`,
  ...) are only accepted before the resource name; after a subcommand argparse
  reports `unrecognized arguments` with no hint. Deferred to the Click migration
  (Click handles this from the box).

## Minor

- [x] **[publish safety]** `publish.yml` now has a test job (lint/format/type/
  tests) that build depends on, a tag↔version check before build, and a final
  `release` job that creates a GitHub Release with the artifacts.
- [x] **[security hardening]** `Client._url` now refuses an absolute URL whose
  host differs from the configured one (blocks token exfiltration), and the
  client warns on stderr when the base URL is plaintext `http://`.
- [ ] **[SIGTERM cleanup]** SIGTERM during `attachment download` leaves a temp
  `.part` file (SIGINT is handled correctly). Install a SIGTERM handler that cleans
  up.
- [ ] **[timeout literal]** The `30.0` timeout default is duplicated as a literal in
  `auth.py` instead of reusing `DEFAULT_TIMEOUT` from `config.py`.
- [x] **[config-file timeout]** A bad `timeout` (and `retries`) from the config
  file is now wrapped in `ConfigError`, matching the env-var path.
- [ ] **[name resolution paging]** Name resolution reads only one collection page
  (`pageSize` 100/200, no paging) in `resolve.py`/`client.py`; a name past the first
  page is not found.
- [ ] **[client typing]** The `client` parameter is untyped in command helpers
  (typed in `resolve.py`); annotate it consistently.
- [ ] **[chunk size]** The `chunk_size 65536` magic number is repeated in two
  `client.py` signatures; extract a constant.
- [ ] **[coverage]** Coverage is configured (`pytest-cov`) but not collected in CI
  and has no threshold. Add `--cov` in CI and a `--cov-fail-under`.
- [x] **[setuptools floor]** Bumped `build-system requires` to `setuptools>=77`
  for the PEP 639 string `license` form.

## Documentation

- [ ] Add status badges to `README.md`: CI status, PyPI version, supported Python
  versions, license.
- [x] Documented env vars (`OPENPROJECT_TIMEOUT`, `OPENPROJECT_RETRIES`,
  `OPENPROJECT_INSECURE`, `OPENPROJECT_URL`, `OPENPROJECT_CONFIG`) in a README
  table, plus the retries and transport-safety behaviour.
- [x] README "Development" now lists `ruff format --check .`.
- [ ] Note that `--max-bytes`/sha256/atomic write apply only to file downloads (not
  the `-` stdout stream); document `auth status --offline`.

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
