"""Command-line contract for the sanitizer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .sync import SyncError, canonical_remote


@dataclass(frozen=True)
class Options:
    sync: bool
    clone: Path | None
    expected_remote: str | None
    confirmed: bool
    keep_tree: bool
    skip_pytest: bool


def parse_args(arguments: list[str] | None = None) -> Options:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="build and verify only (default; non-destructive)")
    mode.add_argument("--sync", action="store_true",
                      help="replace and stage a validated public clone")
    parser.add_argument("--confirm-sync", action="store_true",
                        help="required acknowledgement for destructive --sync")
    parser.add_argument("--public-clone", type=Path,
                        help="absolute path to the disposable public clone")
    parser.add_argument("--expected-remote",
                        help="canonical host/owner/repository expected for origin")
    parser.add_argument("--keep-tree", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args(arguments)
    if args.sync:
        missing = []
        if args.skip_pytest:
            parser.error("--skip-pytest is not allowed with --sync")
        if not args.confirm_sync:
            missing.append("--confirm-sync")
        if args.public_clone is None:
            missing.append("--public-clone")
        if not args.expected_remote:
            missing.append("--expected-remote")
        if missing:
            parser.error("--sync requires " + ", ".join(missing))
        try:
            expected = canonical_remote(args.expected_remote)
        except SyncError as error:
            parser.error(str(error))
        if expected != args.expected_remote:
            parser.error("--expected-remote must use canonical host/owner/repository form")
    elif args.confirm_sync or args.public_clone or args.expected_remote:
        parser.error("sync-only flags require --sync")
    return Options(
        sync=args.sync,
        clone=args.public_clone,
        expected_remote=args.expected_remote,
        confirmed=args.confirm_sync,
        keep_tree=args.keep_tree,
        skip_pytest=args.skip_pytest,
    )
