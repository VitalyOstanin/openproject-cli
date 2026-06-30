# 2. Use Click for argument parsing with options accepted anywhere

Date: 2026-07-01

## Status

Accepted

Supersedes the argument-parsing decision in [ADR-0001](0001-architecture.md).

## Context

ADR-0001 chose the standard-library `argparse` to keep the dependency set small.
In practice `argparse` rejected global options placed after the subcommand:
`openproject-cli wp list --human` failed, and `--human`/`--url`/`--token` had to
precede the resource. This is awkward for interactive use and for scripts and
agents that append flags. Reproducing "options anywhere" on `argparse` requires
duplicating every global option on every subparser and merging the two
namespaces by hand, which is verbose and error-prone.

Click is already a small, widely used dependency (added to `pyproject.toml`),
provides nested groups, parameter sources, and a non-standalone invocation mode
that lets the entry point keep full control of exit codes.

## Decision

- **Click replaces `argparse`.** `cli.py` defines a top-level `click.Group`; each
  resource is a `click.Group` (or a plain `click.Command` for `api`) registered
  under it. The transport/client layering from ADR-0001 is unchanged.
- **Global options anywhere.** A shared decorator attaches the global options
  (`--url`, `--token`, `--config`, `--timeout`, `--retries`, `--insecure`,
  `--human`) to both the top-level group and every leaf command. The group
  records the values it parsed into `ctx.obj`; each leaf merges those defaults
  with any value it parsed, using `ctx.get_parameter_source(...)` to let a value
  given after the subcommand override the one given before it. The merged
  `GlobalOptions` object is what `runtime.client_from_args` / `config_from_args`
  read, so the transport bridge is unaffected.
- **Entry-point contract preserved.** `cli.main(argv) -> int` invokes Click with
  `standalone_mode=False` and maps results to exit codes itself: it never calls
  `sys.exit` for normal flows, translates `OpenProjectCliError` (its own exit
  code), `click.ClickException`/usage errors (2), `--help`/`--version` (0),
  `BrokenPipeError` (silence stdout, 0) and SIGINT/`Abort` (130). A SIGTERM
  handler raises `SystemExit` so streaming-download temp files are cleaned up.
- **Each command emits its own result** through a shared helper that honours the
  effective `--human`, instead of returning data for the entry point to render.

## Consequences

- Global options may be given before the resource or after the subcommand, which
  is the user-visible point of the change.
- The dependency footprint grows by Click (already declared); `argparse` use is
  removed.
- Help text is now formatted by Click rather than `argparse`; the option/command
  set, names, defaults and help strings are preserved, but the exact help layout
  differs.
- Adding a resource or action stays local: a new module with a Click group/command
  plus the shared option decorator, and its tests.
