# openproject-cli

A non-interactive command-line client for the [OpenProject](https://www.openproject.org/)
API v3, in the spirit of [`gh`](https://cli.github.com/). It is designed to be
driven by scripts and AI agents: output is JSON by default, credentials come
from a config file, and any endpoint is reachable through a raw `api`
passthrough.

## Contents

- [Features](#features)
- [Install](#install)
- [Authentication](#authentication)
- [Usage](#usage)
  - [Work packages](#work-packages)
  - [Comments](#comments)
  - [Attachments](#attachments)
  - [Relations](#relations)
  - [Time entries](#time-entries)
  - [Raw API](#raw-api)
- [Output format](#output-format)
- [Configuration](#configuration)
- [Development](#development)
- [License](#license)

## Features

- CRUDL for work packages, comments, attachments, relations and time entries.
- JSON output by default; `--human` for a flat, dependency-free text rendering.
- Server-side filtering (the API does the filtering, not the client), including
  filtering work packages and time entries by assignee/user resolved from `me`,
  a numeric id, or an exact name.
- Streaming file transfers: downloads and uploads are never buffered whole in
  memory. Downloads are atomic (temp file + rename), report a `sha256`, and
  accept `--max-bytes`.
- Custom field values with names resolved from the schema, and comment/activity
  author names resolved by id.
- Raw `api` passthrough to any endpoint, modelled on `gh api`.
- Detailed `--help` at every level (global, per resource, per action).
- Safe for scripts and agents: every command is non-interactive except
  `auth login`, which prompts for the token only when one is not supplied.

## Install

Requires Python 3.11+. Install with [uv](https://docs.astral.sh/uv/) so the
`openproject-cli` command lands on your `PATH`:

```sh
uv tool install openproject-cli
# or from a local checkout:
uv tool install --from . openproject-cli
```

With pip:

```sh
pip install openproject-cli
```

## Authentication

Like `gh`. The simplest path is interactive — `auth login` opens the OpenProject
API token page (*My account → Access tokens → API*) in a browser and prompts for
the token to paste:

```sh
openproject-cli auth login --url https://openproject.example.com
# opens .../my/access_token in a browser, then: "Paste your API token:" (hidden)
```

The base URL is saved to the config file, so `--url` only has to be given once;
afterwards `auth login` (and every other command) reuses it from the config or
`$OPENPROJECT_URL`. Use `--no-browser` to skip opening the browser.

For scripts, pass the token non-interactively instead:

```sh
openproject-cli auth login --url https://openproject.example.com --with-token < token.txt
# or pass it directly (less safe; ends up in shell history):
openproject-cli auth login --url https://openproject.example.com --token YOUR_TOKEN

openproject-cli auth status     # show config and token source, verify against server
openproject-cli auth token      # print the resolved token
openproject-cli auth logout     # remove the stored token
```

By default the token is stored in the **system keyring** (keyed by host URL);
the config file then holds only non-secret settings (including the base URL).
Pass `--insecure-storage` to write the token into the config file instead — the
tool also falls back to the file automatically when no keyring backend is
available (e.g. headless servers).

Credentials can also be supplied per command via `--url`/`--token` or the
`OPENPROJECT_URL`/`OPENPROJECT_TOKEN` environment variables. The token is
resolved in this order: `--token` flag, environment, keyring, config file.

OpenProject has no browser OAuth device flow comparable to GitHub's, so (unlike
`gh`) login does not perform an OAuth handshake — it opens the API token page and
takes the token you generate there.

## Usage

Global options go **before** the resource:

```
openproject-cli [--url URL] [--token TOKEN] [--config PATH] [--human] <resource> <action> [options]
```

### Work packages

```sh
openproject-cli wp list --assignee me --open
openproject-cli wp list --project my-project --status "In progress"
openproject-cli wp get 1234
openproject-cli wp create --project my-project --type Task --subject "Fix X"
openproject-cli wp update 1234 --status "In progress" --done-ratio 50
openproject-cli wp delete 1234
```

### Comments

```sh
openproject-cli comment list --work-package 1234 --comments-only
openproject-cli comment create --work-package 1234 "Ready for review"
openproject-cli comment update 9876 "Edited comment"
```

The OpenProject API has no comment-deletion endpoint, so there is no
`comment delete`.

### Attachments

```sh
openproject-cli attachment list --work-package 1234
openproject-cli attachment upload --work-package 1234 ./report.pdf
openproject-cli attachment download 9876 --output report.pdf   # '-' for stdout
openproject-cli attachment delete 9876
```

### Relations

```sh
openproject-cli relation list --work-package 1234
openproject-cli relation create --work-package 1234 --to 5678 --type follows
openproject-cli relation delete 42
```

### Time entries

```sh
openproject-cli time list --user me --since 2026-01-01
openproject-cli time create --work-package 1234 --hours 1.5 --comment "review"
openproject-cli time update 4242 --hours 2
openproject-cli time delete 4242
```

### Raw API

```sh
openproject-cli api GET work_packages/1234
openproject-cli api GET work_packages -f pageSize=5
openproject-cli api POST time_entries --input body.json
```

## Output format

JSON is printed to stdout by default; errors go to stderr and the process exits
non-zero. `--human` switches to a flat text rendering (mappings become
`key: value` lines, lists of objects become tab-separated rows). `--raw` on read
commands returns the unmodified API payload instead of the normalized subset.

## Configuration

The config file lives at `~/.config/openproject-cli/config.yaml` (override with
`--config` or `OPENPROJECT_CONFIG`; `XDG_CONFIG_HOME` is honoured). Values are
resolved in order: command-line flag, environment variable, config file.

```yaml
url: https://openproject.example.com
timeout: 30
verify_ssl: true
# token: only present with --insecure-storage; otherwise it lives in the keyring
```

The file is written with `0600` permissions, and with keyring storage it holds
no secret.

## Development

```sh
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
ruff check . && pyright && pytest
```

## License

[MIT](LICENSE)
