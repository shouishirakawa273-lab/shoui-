"""Financial Summary(`/v2/fins/summary`)の時系列を人間が目視確認するための診断Script。

`scripts/fetch_jquants_local_snapshot.py --fetch-financial-summary`で取得した
`financial_summary_<code>.json`(ローカルSnapshot、`.gitignore`対象)を読み込み、
DiscDate/DiscTime/DiscNo/DocType/CurPerType/主要Forecast Fieldの変化を
時系列で表示するだけの診断専用Scriptである。

**「上方修正を自動検出して投資判断」には進まない。** 数値の変化を検知・分類・
評価するロジックは一切持たない(それはStrategy探索であり、Phase4Aのスコープ外)。
このScript自体は外部APIへ接続しない(ローカルファイルを読むだけ)。

使い方:
    python scripts/jquants_financial_summary_diagnostic.py \\
        --snapshot-dir Japanese_Equity_Lab/01_data/raw/local_snapshot_input \\
        --code 6758
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

_DISPLAY_FIELDS = (
    "DiscNo",
    "DocType",
    "DiscDate",
    "DiscTime",
    "CurPerType",
    "Sales",
    "OP",
    "NP",
    "FSales",
    "FOP",
    "FNP",
    "NxFSales",
    "NxFOP",
    "NxFNP",
)


def _load_rows(snapshot_dir: Path, code: str) -> list[dict[str, Any]]:
    for suffix in (".json",):
        path = snapshot_dir / f"financial_summary_{code}{suffix}"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload.get("data") if isinstance(payload, dict) else payload
            if records is None:
                raise SystemExit(f"{path} に'data'キーが見つかりません(J-Quants V2の生レスポンスをそのまま保存してください)")
            return list(records)
    raise SystemExit(
        f"{snapshot_dir} に financial_summary_{code}.json が見つかりません。"
        "先に `python scripts/fetch_jquants_local_snapshot.py --fetch-financial-summary --codes "
        f"{code}` 等で取得してください。"
    )


def print_timeline(snapshot_dir: Path, code: str) -> None:
    rows = _load_rows(snapshot_dir, code)
    rows_sorted = sorted(rows, key=lambda r: (str(r.get("DiscDate") or ""), str(r.get("DiscTime") or "")))

    print(f"code={code}: {len(rows_sorted)}件のDisclosureを時系列で表示(古い順)\n")
    header = " | ".join(f"{field:>10}" for field in _DISPLAY_FIELDS)
    print(header)
    print("-" * len(header))
    for row in rows_sorted:
        line = " | ".join(f"{str(row.get(field, '')):>10}" for field in _DISPLAY_FIELDS)
        print(line)

    print(
        "\n(このScriptは表示のみを行う。上方修正/下方修正の自動検出・分類・投資判断は行わない。"
        "DiscNo/DocTypeからRevision Relationshipを確定できるかは未確認のため、"
        "Disclosureはそのまま独立した時系列として表示している。DECISIONS.md D0043参照)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=_LAB_DIR / "01_data" / "raw" / "local_snapshot_input",
    )
    parser.add_argument("--code", required=True)
    args = parser.parse_args()
    print_timeline(args.snapshot_dir, args.code)


if __name__ == "__main__":
    main()
