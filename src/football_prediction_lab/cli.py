"""Command-line entry point for the research lab."""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="football-lab",
        description="Auditable football prediction research lab.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    status = subparsers.add_parser("status", help="Show the current project scope.")
    status.set_defaults(handler=_status)
    return parser


def _status(_: argparse.Namespace) -> int:
    print("target_market=btts")
    print("prediction_horizon=pre_match")
    print("execution_mode=research_only")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
