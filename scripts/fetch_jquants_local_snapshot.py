"""J-Quants実データを取得し、LocalSnapshotAdapterが読める形式でローカルへ保存する。

このリポジトリの開発セッションはネットワークポリシーによりJ-Quants等の外部APIへ
一切疎通できない(README.md / Japanese_Equity_Lab/DECISIONS.md D0012, D0025参照)。
このスクリプトは**ネットワーク接続可能なローカル環境で**実行することを前提とし、
`.env`の`JQUANTS_REFRESH_TOKEN`を使って実際にJ-Quants APIへ接続し、取得結果を
`lib/data_sources/local_snapshot.LocalSnapshotAdapter`が読めるファイル命名規約
(daily_quotes_<code>.json / trading_calendar.json / indices_<index_code>.json /
listed_info.json)でディレクトリへ保存する。

このスクリプト自体は`lib/data_sources/jquants.JQuantsAdapter`をそのまま再利用するため、
エンドポイント・パラメータ名の知識を二重管理しない。認証情報(リフレッシュトークン・
IDトークン)はいかなるファイルにも書き出さない(市場データのペイロードのみ保存する)。

出力先はデフォルトで`Japanese_Equity_Lab/01_data/raw/local_snapshot_input/`とし、
`.gitignore`で追跡除外済み(実データのためコミットしない)。ここに保存したファイルは
「ユーザー手元の作業コピー」であり、Pipeline実行時に`--source local`経由で読み込まれると
`lib/snapshot.RawSnapshotStore`が別途Immutable Raw Snapshot(`01_data/raw/local/`)として
正式に記録する(このスクリプトの出力そのものが記録用Snapshotではない)。

使い方(ローカル環境、.envにJQUANTS_REFRESH_TOKEN設定済みであること):
    python scripts/fetch_jquants_local_snapshot.py \\
        --codes 7203 6758 8056 3626 --benchmark-index-code 0000 \\
        --start 2022-01-04 --end 2024-12-30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from dotenv import load_dotenv  # noqa: E402
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.errors import DataSourceError  # noqa: E402

_CALENDAR_BUFFER_DAYS = 45  # 前後の取引日解決(lookback/holding)に余裕を持たせる


def _save(path: Path, *, key: str, records: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({key: records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {path} ({len(records)}件)")


def fetch_all(*, codes: list[str], benchmark_index_code: str, start: date, end: date, output_dir: Path) -> None:
    load_dotenv()
    adapter = JQuantsAdapter()
    if not adapter.configured:
        raise SystemExit(
            "JQUANTS_REFRESH_TOKEN が設定されていません。リポジトリルートの.envに設定してください"
            "(絶対にリポジトリへコミットしないこと)。"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    calendar_start = start - timedelta(days=_CALENDAR_BUFFER_DAYS)
    calendar_end = end + timedelta(days=_CALENDAR_BUFFER_DAYS)

    print(f"取引カレンダー取得: {calendar_start} 〜 {calendar_end}")
    try:
        calendar_result = adapter.fetch_trading_calendar(start_date=calendar_start, end_date=calendar_end)
    except DataSourceError as exc:
        raise SystemExit(f"取引カレンダー取得に失敗しました: {exc}") from exc
    _save(output_dir / "trading_calendar.json", key="trading_calendar", records=calendar_result.payload)

    print(f"個別銘柄日次株価取得: {codes} ({start} 〜 {end})")
    for code in codes:
        try:
            quotes_result = adapter.fetch_daily_quotes(codes=[code], start_date=start, end_date=end)
        except DataSourceError as exc:
            raise SystemExit(f"{code} の日次株価取得に失敗しました: {exc}") from exc
        _save(output_dir / f"daily_quotes_{code}.json", key="daily_quotes", records=quotes_result.payload)

    print(f"指数(benchmark)取得: index_code={benchmark_index_code} ({start} 〜 {end})")
    try:
        index_result = adapter.fetch_index_prices(index_code=benchmark_index_code, start_date=start, end_date=end)
    except DataSourceError as exc:
        raise SystemExit(f"指数({benchmark_index_code})取得に失敗しました: {exc}") from exc
    _save(output_dir / f"indices_{benchmark_index_code}.json", key="indices", records=index_result.payload)

    print("銘柄マスタ(/listed/info)取得")
    try:
        listed_result = adapter.fetch_listed_info()
    except DataSourceError as exc:
        raise SystemExit(f"銘柄マスタ取得に失敗しました: {exc}") from exc
    _save(output_dir / "listed_info.json", key="info", records=listed_result.payload)

    print("\n完了。以下のコマンドでPipelineを実行できます:\n")
    print(
        "python scripts/jquants_lab_pipeline.py --source local "
        f"--local-snapshot-dir {output_dir} --codes {' '.join(codes)} "
        f"--benchmark-index-code {benchmark_index_code} --start {start.isoformat()} --end {end.isoformat()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="+", default=["7203", "6758", "8056", "3626"])
    parser.add_argument("--benchmark-index-code", default="0000")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_LAB_DIR / "01_data" / "raw" / "local_snapshot_input",
    )
    args = parser.parse_args()
    fetch_all(
        codes=args.codes,
        benchmark_index_code=args.benchmark_index_code,
        start=args.start,
        end=args.end,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
