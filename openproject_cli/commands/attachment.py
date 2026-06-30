"""CRUDL for work-package attachments (``attachment``).

Downloads and uploads are streamed: ``download`` writes the response body to
disk (or stdout) chunk by chunk, and ``upload`` hands the open file to the HTTP
layer so it is read incrementally. Neither path loads a whole file into memory.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from openproject_cli import normalize, runtime
from openproject_cli.commands._args import add_paging, add_raw, paging_params


def cmd_list(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"work_packages/{args.work_package}/attachments", params=paging_params(args))
    elements = normalize.collection(payload)
    if args.raw:
        return elements
    return [normalize.attachment(item) for item in elements]


def cmd_get(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.get_json(f"attachments/{args.id}")
    return payload if args.raw else normalize.attachment(payload)


def cmd_download(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    path = f"attachments/{args.id}/content"
    if args.output == "-":
        # Binary content goes to stdout; status text goes to stderr so the
        # stream stays clean for piping.
        written = client.stream_download(path, sys.stdout.buffer)
        sys.stdout.buffer.flush()
        print(f"streamed {written} bytes to stdout", file=sys.stderr)
        return None
    # Write to a temp file and atomically rename on success, so an interrupted
    # download never leaves a partial file in place.
    result = client.download_to_path(path, args.output, max_bytes=args.max_bytes)
    return {
        "downloaded": args.id,
        "path": args.output,
        "bytes": result["bytes"],
        "sha256": result["sha256"],
    }


def cmd_upload(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    payload = client.upload_attachment(
        args.work_package,
        args.file,
        file_name=args.name,
        description=args.description,
        content_type=args.content_type,
    )
    return payload if args.raw else normalize.attachment(payload)


def cmd_delete(args: argparse.Namespace) -> Any:
    client = runtime.client_from_args(args)
    client.delete(f"attachments/{args.id}")
    return {"deleted": args.id}


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "attachment",
        help="work-package files: list, get, download, upload, delete",
        description="List, read, download, upload and delete work-package attachments.",
    )
    actions = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    p_list = actions.add_parser(
        "list",
        help="list attachments of a work package",
        description="List attachments of a work package.",
        epilog="Example: openproject-cli attachment list --work-package 1234",
    )
    p_list.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    add_paging(p_list)
    add_raw(p_list)
    p_list.set_defaults(func=cmd_list)

    p_get = actions.add_parser(
        "get", help="show attachment metadata", description="Show metadata of a single attachment."
    )
    p_get.add_argument("id", type=int, help="attachment id")
    add_raw(p_get)
    p_get.set_defaults(func=cmd_get)

    p_download = actions.add_parser(
        "download",
        help="download attachment content (streamed)",
        description="Stream an attachment's content to a file or to stdout ('-').",
        epilog="Example: openproject-cli attachment download 987 --output report.pdf",
    )
    p_download.add_argument("id", type=int, help="attachment id")
    p_download.add_argument("--output", "-o", required=True, help="destination file path, or '-' for stdout")
    p_download.add_argument(
        "--max-bytes",
        dest="max_bytes",
        type=int,
        default=None,
        help="abort the download if the content exceeds this many bytes",
    )
    p_download.set_defaults(func=cmd_download)

    p_upload = actions.add_parser(
        "upload",
        help="upload a file as an attachment (streamed)",
        description="Stream a local file to a work package as an attachment.",
        epilog="Example: openproject-cli attachment upload --work-package 1234 ./report.pdf",
    )
    p_upload.add_argument(
        "--work-package", dest="work_package", type=int, required=True, help="work package id"
    )
    p_upload.add_argument("file", help="path to the local file to upload")
    p_upload.add_argument("--name", help="attachment file name (default: the local file name)")
    p_upload.add_argument("--description", help="attachment description")
    p_upload.add_argument(
        "--content-type", dest="content_type", help="MIME type (default: guessed from name)"
    )
    add_raw(p_upload)
    p_upload.set_defaults(func=cmd_upload)

    p_delete = actions.add_parser(
        "delete", help="delete an attachment", description="Delete an attachment by id."
    )
    p_delete.add_argument("id", type=int, help="attachment id")
    p_delete.set_defaults(func=cmd_delete)
