"""CRUDL for work-package attachments (``attachment``).

Downloads and uploads are streamed: ``download`` writes the response body to
disk (or stdout) chunk by chunk, and ``upload`` hands the open file to the HTTP
layer so it is read incrementally. Neither path loads a whole file into memory.
"""

from __future__ import annotations

import sys

import click

from openproject_cli import normalize, runtime
from openproject_cli.commands._common import (
    common_options,
    emit_result,
    paging_options,
    paging_params,
    raw_option,
    resolve_globals,
)
from openproject_cli.output import silence_broken_pipe


@click.group("attachment", short_help="work-package files: list, get, download, upload, delete")
def attachment() -> None:
    """List, read, download, upload and delete work-package attachments."""


@attachment.command(
    "list",
    short_help="list attachments of a work package",
    epilog="Example: openproject-cli attachment list --work-package 1234",
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@paging_options
@raw_option
@common_options()
@click.pass_context
def attachment_list(
    ctx: click.Context, work_package: int, offset: int, limit: int | None, raw: bool, **_globals: object
) -> None:
    """List attachments of a work package."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(
        f"work_packages/{work_package}/attachments", params=paging_params(offset, limit)
    )
    elements = normalize.collection(payload)
    if raw:
        emit_result(elements, gopts)
        return
    emit_result([normalize.attachment(item) for item in elements], gopts)


@attachment.command("get", short_help="show attachment metadata")
@click.argument("attachment_id", type=int, metavar="ID")
@raw_option
@common_options()
@click.pass_context
def attachment_get(ctx: click.Context, attachment_id: int, raw: bool, **_globals: object) -> None:
    """Show metadata of a single attachment."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.get_json(f"attachments/{attachment_id}")
    emit_result(payload if raw else normalize.attachment(payload), gopts)


@attachment.command(
    "download",
    short_help="download attachment content (streamed)",
    epilog="Example: openproject-cli attachment download 987 --output report.pdf",
)
@click.argument("attachment_id", type=int, metavar="ID")
@click.option("--output", "-o", required=True, help="destination file path, or '-' for stdout")
@click.option(
    "--max-bytes",
    "max_bytes",
    type=int,
    default=None,
    help="abort the download if the content exceeds this many bytes",
)
@common_options()
@click.pass_context
def attachment_download(
    ctx: click.Context, attachment_id: int, output: str, max_bytes: int | None, **_globals: object
) -> None:
    """Stream an attachment's content to a file or to stdout ('-')."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    path = f"attachments/{attachment_id}/content"
    if output == "-":
        # Binary content goes to stdout; status text goes to stderr so the
        # stream stays clean for piping.
        try:
            written = client.stream_download(path, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        except BrokenPipeError:
            silence_broken_pipe()
            return
        print(f"streamed {written} bytes to stdout", file=sys.stderr)
        return
    # Write to a temp file and atomically rename on success, so an interrupted
    # download never leaves a partial file in place.
    result = client.download_to_path(path, output, max_bytes=max_bytes)
    emit_result(
        {
            "downloaded": attachment_id,
            "path": output,
            "bytes": result["bytes"],
            "sha256": result["sha256"],
        },
        gopts,
    )


@attachment.command(
    "upload",
    short_help="upload a file as an attachment (streamed)",
    epilog="Example: openproject-cli attachment upload --work-package 1234 ./report.pdf",
)
@click.option("--work-package", "work_package", type=int, required=True, help="work package id")
@click.argument("file")
@click.option("--name", help="attachment file name (default: the local file name)")
@click.option("--description", help="attachment description")
@click.option("--content-type", "content_type", help="MIME type (default: guessed from name)")
@raw_option
@common_options()
@click.pass_context
def attachment_upload(
    ctx: click.Context,
    work_package: int,
    file: str,
    name: str | None,
    description: str | None,
    content_type: str | None,
    raw: bool,
    **_globals: object,
) -> None:
    """Stream a local file to a work package as an attachment."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    payload = client.upload_attachment(
        work_package,
        file,
        file_name=name,
        description=description,
        content_type=content_type,
    )
    emit_result(payload if raw else normalize.attachment(payload), gopts)


@attachment.command("delete", short_help="delete an attachment")
@click.argument("attachment_id", type=int, metavar="ID")
@common_options()
@click.pass_context
def attachment_delete(ctx: click.Context, attachment_id: int, **_globals: object) -> None:
    """Delete an attachment by id."""
    gopts = resolve_globals(ctx)
    client = runtime.client_from_args(gopts)
    client.delete(f"attachments/{attachment_id}")
    emit_result({"deleted": attachment_id}, gopts)
