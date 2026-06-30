# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Automatic retries for idempotent requests (`GET`/`HEAD`/`OPTIONS`/`PUT`/
  `DELETE`) on transport errors and transient statuses (`429`/`5xx`), honouring
  `Retry-After` with exponential backoff. Configurable via `--retries` /
  `OPENPROJECT_RETRIES` (default 3, `0` disables); `POST` is never retried.

### Security

- The client refuses to send the API token to a host other than the configured
  one (an absolute URL passed to `api` pointing elsewhere is rejected) and warns
  on stderr when the base URL uses plaintext `http://`.

### Fixed

- `comment create` posted to a non-existent endpoint
  (`work_packages/{id}/comment`); it now uses `work_packages/{id}/activities`,
  which the API requires (the old path returned HTTP 404).

### Changed

- CI installs into a virtual environment and runs tools via `uv run`; the
  previous `uv pip install --system` failed as "externally managed" so lint,
  type check and tests were skipped. Added `timeout-minutes` to the CI job.
- The test suite runs via a bare `pytest` invocation again (added `pythonpath`),
  and a default per-test timeout is enforced via `pytest-timeout`.
- Build requires `setuptools>=77` for the PEP 639 string `license` field.
- A bad `timeout` value read from the config file now raises a clear
  `ConfigError` instead of an unhandled traceback (matching the env-var path).
- GitHub Actions are pinned by commit SHA (with a version comment). The publish
  workflow now gates on a green test job, checks the tag matches the project
  version, and creates a GitHub Release.

## [0.1.0]

Initial release.

### Added

- Non-interactive CLI (`openproject-cli`) over the OpenProject API v3.
- CRUDL commands for work packages (`wp`), comments (`comment`), attachments
  (`attachment`), relations (`relation`) and time entries (`time`).
- Raw `api` passthrough to any endpoint, modelled on `gh api`.
- `auth login` / `auth status` / `auth token` / `auth logout`, modelled on
  `gh auth`. The token is stored in the system keyring by default (keyed by host
  URL), with `--insecure-storage` and an automatic file fallback when no keyring
  backend is available; `--with-token` reads the token from stdin. Token
  resolution order: flag, environment, keyring, config file.
- Interactive `auth login`: with no token flag it opens the OpenProject API
  token page (`/my/access_token`) in a browser and prompts for the token to
  paste (hidden input). The base URL is saved to the config file, so `--url`
  only has to be given once (afterwards it is reused from the config or
  `$OPENPROJECT_URL`). `--no-browser` skips opening the browser.
- JSON output by default, `--human` for flat text, `--raw` for unmodified
  payloads.
- Server-side filtering for work packages and time entries, with
  assignee/user resolution from `me`, a numeric id, or an exact name.
- Streaming attachment download and upload (no full-file buffering in memory).
  Downloads are written via a temporary file and atomically renamed on success
  (no partial files on failure), report the content `sha256`, and accept
  `--max-bytes` to cap the transfer.
- Work-package output includes `customFields` with names resolved from the
  schema (one cached request per distinct schema; none when a work package has
  no custom fields).
- Comment/activity output resolves the author name from the user id (the API
  omits it on activity links) and exposes `details` (field-change descriptions).
- `DELETE` requests send `Content-Type: application/json`, which OpenProject
  requires (it answers HTTP 406 otherwise).
- Paths/hrefs are normalized to handle instances hosted under a deployment
  sub-path: an href that already carries the API prefix (e.g.
  `/openproject/api/v3/...`, as returned by such instances) is reduced to its
  api-absolute form instead of having the prefix duplicated (which caused 404).
- Detailed `--help` at the global, resource and action levels.
