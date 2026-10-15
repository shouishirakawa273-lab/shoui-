"""Compare explicit macro samples against a saved plan at actual current UTC."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from decimal import DecimalException
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.evaluation.integrity import to_hashable  # noqa: E402
from lib.macro_experiments.comparison import compare_macro_forecasts  # noqa: E402
from lib.macro_experiments.input import read_samples  # noqa: E402
from lib.macro_experiments.store import read_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = read_plan(args.store, args.id)
        samples = read_samples(args.input)
        result = compare_macro_forecasts(plan=plan, samples=samples, evaluated_at=datetime.now(UTC))
        sys.stdout.write(json.dumps(to_hashable(result), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    except (ValueError, TypeError, KeyError, OSError, DecimalException) as exc:
        logging.error("macro comparison: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
