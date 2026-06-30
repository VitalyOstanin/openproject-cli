"""Shared argparse helpers reused across resource subcommands."""

from __future__ import annotations

import argparse


def add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--offset", type=int, default=1, help="1-based page offset (default: 1)")
    parser.add_argument("--limit", type=int, default=None, help="page size (default: server default)")


def add_raw(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--raw",
        action="store_true",
        help="output the raw API payload without field normalization",
    )


def paging_params(args: argparse.Namespace) -> dict[str, str]:
    params: dict[str, str] = {"offset": str(args.offset)}
    if args.limit is not None:
        params["pageSize"] = str(args.limit)
    return params
