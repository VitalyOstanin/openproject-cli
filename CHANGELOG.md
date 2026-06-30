# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- The client no longer follows HTTP redirects. The API v3 does not redirect, and
  following a redirect blindly could replay the Basic-auth token to the redirect
  target (an SSRF / token-exfiltration vector); a 3xx now surfaces as an error.
- A scheme-less base URL is defaulted to `https://`. Without a scheme the host
  comparison that prevents sending the token to another host was silently
  disabled (fail-open); it is now always active.

### Fixed

- A single retry sleep is capped (60s), so a large `--retries` (exponential
  backoff) or a far-future `Retry-After` date can no longer hang the CLI.
- Collection paging and error-message extraction tolerate an `_embedded` /
  `total` field that is present but explicitly `null` (previously raised).

### Changed

- An unexpected (non-domain) error prints a one-line summary instead of a raw
  traceback; set `OPENPROJECT_DEBUG=1` to re-raise the full traceback.
- A retry now emits a one-line warning to stderr (method, URL, reason, attempt),
  so transient failures are no longer silent.
- The publish workflow's test job enforces the same coverage floor as CI
  (`--cov-fail-under=75`); both workflows declare a least-privilege top-level
  `permissions: contents: read`; the release job dropped a redundant checkout.

## [0.1.0] - 2026-07-01

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
  assignee/user resolution from `me`, a numeric id, or an exact name (paginated
  across all result pages).
- Global options (`--url`, `--token`, `--config`, `--timeout`, `--retries`,
  `--insecure`, `--human`) work anywhere — before the resource or after the
  subcommand (e.g. `openproject-cli wp list --human`); a value given after the
  subcommand overrides one given before it. (Argument parsing is built on Click.)
- Automatic retries for idempotent requests (`GET`/`HEAD`/`OPTIONS`/`PUT`/
  `DELETE`) on transport errors and transient statuses (`429`/`5xx`), honouring
  `Retry-After` with exponential backoff. Configurable via `--retries` /
  `OPENPROJECT_RETRIES` (default 3, `0` disables); `POST` is never retried.
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

### Security

- The client refuses to send the API token to a host other than the configured
  one (an absolute URL passed to `api` pointing elsewhere is rejected) and warns
  on stderr when the base URL uses plaintext `http://`.
