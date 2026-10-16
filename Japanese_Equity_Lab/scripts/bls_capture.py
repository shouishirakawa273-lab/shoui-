"""Capture-only BLS CPI register and read-only bundle inspection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.macro_capture.bls import capture, show  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("fetch", "show"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", type=Path, required=True)
        sub.add_argument("--run-id", required=command == "show")
    args = parser.parse_args()
    try:
        result = capture(args.root, args.run_id) if args.command == "fetch" else show(args.root, args.run_id)
        print(json.dumps(result, ensure_ascii=False))
        if result["outcome"] == "FAILED":
            print(result["error"], file=sys.stderr)
            return 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
