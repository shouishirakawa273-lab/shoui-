"""Financial Summary(`/v2/fins/summary`)の時系列を人間が目視確認するための診断Script。

`scripts/fetch_jquants_local_snapshot.py --fetch-financial-summary`で取得した
`financial_summary_<code>.json`(ローカルSnapshot、`.gitignore`対象)を読み込み、
DiscDate/DiscTime/DiscNo/DocType/CurPerType/主要Forecast Fieldの変化を
時系列で表示するだけの診断専用Scriptである。

**「上方修正を自動検出して投資判断」には進まない。** 数値の変化を検知・分類・
評価するロジックは一切持たない(それはStrategy探索であり、Phase4Aのスコープ外)。
このScript自体は外部APIへ接続しない(ローカルファイルを読むだけ)。

**Raw CoverageとResearch Windowを区別する(2026-08-16 Local Real Data
Validationで確認済み、D0043参照)**: `/v2/fins/summary`はcode指定クエリの場合、
取得時に指定した期間へ絞り込まれず、対象Codeの取得可能な全履歴を返す。したがって
Raw SnapshotのCoverageが取得時のResearch Windowを超えていても、それ自体は
異常ではない(Warningではなく正常な状態として扱う)。`--research-window-start`/
`--research-window-end`を指定すると、その範囲を参考表示するのみで、行の絞り込みは
行わない。

使い方:
    python scripts/jquants_financial_summary_diagnostic.py \\
        --snapshot-dir Japanese_Equity_Lab/01_data/raw/local_snapshot_input \\
        --code 6758 \\
        --research-window-start 2024-01-01 --research-window-end 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from lib.fundamentals.normalize import raw_disclosure_date_range  # noqa: E402

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


def print_timeline(
    snapshot_dir: Path,
    code: str,
    *,
    research_window_start: date | None = None,
    research_window_end: date | None = None,
) -> None:
    rows = _load_rows(snapshot_dir, code)
    rows_sorted = sorted(rows, key=lambda r: (str(r.get("DiscDate") or ""), str(r.get("DiscTime") or "")))

    raw_min, raw_max = raw_disclosure_date_range(rows)
    print(f"code={code}: {len(rows_sorted)}件のDisclosureを時系列で表示(古い順)")
    print(f"  Raw Coverage(実際に取得できたDisclosureの範囲): {raw_min} 〜 {raw_max}")
    if research_window_start is not None or research_window_end is not None:
        print(f"  Research Window(参考表示のみ、絞り込みはしない): {research_window_start} 〜 {research_window_end}")
        print(
            "  (Raw CoverageがResearch Windowを超えていても異常ではない。"
            "/v2/fins/summaryはcode指定時、期間で絞り込まれない。D0043参照)"
        )
    print()
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
    parser.add_argument(
        "--research-window-start",
        type=date.fromisoformat,
        default=None,
        help="参考表示のみ(Rawの絞り込みは行わない)。",
    )
    parser.add_argument(
        "--research-window-end",
        type=date.fromisoformat,
        default=None,
        help="参考表示のみ(Rawの絞り込みは行わない)。",
    )
    args = parser.parse_args()
    print_timeline(
        args.snapshot_dir,
        args.code,
        research_window_start=args.research_window_start,
        research_window_end=args.research_window_end,
    )


if __name__ == "__main__":
    main()
