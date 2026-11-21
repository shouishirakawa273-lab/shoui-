"""Inspect one serialized request without creating stores or modifying files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.profit_impact.preflight import decode_request, inspect_request  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        report = inspect_request(decode_request(args.request.read_text(encoding="utf-8")))
    except (ValueError, TypeError, OSError, ArithmeticError) as exc:
        print(json.dumps({"input_status": "INVALID", "error_type": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
