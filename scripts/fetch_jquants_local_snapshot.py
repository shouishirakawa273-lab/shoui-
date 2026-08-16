"""J-Quants API V2の実データを取得し、LocalSnapshotAdapterが読める形式でローカルへ保存する。

このリポジトリの開発セッションはネットワークポリシーによりJ-Quants等の外部API・
公式ドキュメントへ一切疎通できない(README.md / Japanese_Equity_Lab/DECISIONS.md
D0012, D0025, D0031参照)。このスクリプトは**ネットワーク接続可能なローカル環境で**
実行することを前提とし、`.env`の`JQUANTS_API_KEY`を使って実際にJ-Quants API V2へ
接続し、取得結果を`lib/data_sources/local_snapshot.LocalSnapshotAdapter`が読める
ファイル命名規約(equity_bars_<code>.json / trading_calendar.json / topix_bars.json /
equities_master.json)でディレクトリへ保存する。

このスクリプト自体は`lib/data_sources/jquants.JQuantsAdapter`をそのまま再利用するため、
Endpoint・パラメータ名の知識を二重管理しない(pagination_keyによる複数ページの結合も
Adapter側で行われる)。認証情報(APIキー)はいかなるファイルにも書き出さない
(市場データのペイロードのみ保存する)。

出力先はデフォルトで`Japanese_Equity_Lab/01_data/raw/local_snapshot_input/`とし、
`.gitignore`で追跡除外済み(実データのためコミットしない)。ここに保存したファイルは
「ユーザー手元の作業コピー」であり、Pipeline実行時に`--source local`経由で読み込まれると
`lib/snapshot.RawSnapshotStore`が別途Immutable Raw Snapshot(`01_data/raw/jquants_local/`)
として正式に記録する(このスクリプトの出力そのものが記録用Snapshotではない)。

現在の契約プラン(Light、ユーザー申告)でこれらのEndpointが利用可能かどうかは、
このセッションでは検証できていない(`DataSourceCapabilities`、DECISIONS.md D0033参照)。
利用不可の場合はJ-Quants自身がエラーを返すので、その内容をそのまま確認できる。

使い方(ローカル環境、.envにJQUANTS_API_KEY設定済みであること):
    python scripts/fetch_jquants_local_snapshot.py \\
        --codes 7203 6758 8056 3626 \\
        --start 2022-01-04 --end 2024-12-30

`--master-pit-check`(Phase3C/D0038): `/v2/equities/master`の`date`パラメータが
真のPoint-in-Time上場状況(過去に存在したが現在は廃止済みの銘柄を含む)を返すのか、
単に「現在の上場状況」を返すだけなのかは未検証(DECISIONS.md D0038参照)。この
フラグは、廃止日を挟む前後2つの日付でMasterを取得し、指定Codeが含まれるかどうかを
比較表示するだけの診断専用モードで、`--output-dir`へは何も書き込まない
(`LocalSnapshotAdapter`用のSnapshotを汚さない)。過去に上場廃止されたことが
分かっている銘柄コードで実行することを想定している:
    python scripts/fetch_jquants_local_snapshot.py \\
        --master-pit-check 2023-01-01 2024-01-01 --master-pit-check-code 1234
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
from lib.data_sources.ticker_codes import TickerCodeNormalizationError, normalize_provider_code_to_internal  # noqa: E402
from lib.errors import DataSourceError  # noqa: E402

_CALENDAR_BUFFER_DAYS = 45  # 前後の取引日解決(lookback/holding)に余裕を持たせる


def _save(path: Path, *, records: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"data": records, "pagination_key": None}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {path} ({len(records)}件)")


def fetch_all(*, codes: list[str], start: date, end: date, output_dir: Path) -> None:
    load_dotenv()
    adapter = JQuantsAdapter()
    if not adapter.configured:
        raise SystemExit(
            "JQUANTS_API_KEY が設定されていません。リポジトリルートの.envに設定してください"
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
    _save(output_dir / "trading_calendar.json", records=calendar_result.payload)

    print(f"個別銘柄日次Bar取得: {codes} ({start} 〜 {end})")
    for code in codes:
        try:
            bars_result = adapter.fetch_equity_bars(codes=[code], start_date=start, end_date=end)
        except DataSourceError as exc:
            raise SystemExit(f"{code} の日次Bar取得に失敗しました: {exc}") from exc
        _save(output_dir / f"equity_bars_{code}.json", records=bars_result.payload)

    print(f"TOPIX取得: {start} 〜 {end}")
    try:
        topix_result = adapter.fetch_topix_bars(start_date=start, end_date=end)
    except DataSourceError as exc:
        raise SystemExit(f"TOPIX取得に失敗しました: {exc}") from exc
    _save(output_dir / "topix_bars.json", records=topix_result.payload)

    print("銘柄マスタ(/v2/equities/master)取得")
    try:
        master_result = adapter.fetch_equities_master()
    except DataSourceError as exc:
        raise SystemExit(f"銘柄マスタ取得に失敗しました: {exc}") from exc
    _save(output_dir / "equities_master.json", records=master_result.payload)

    print("\n完了。以下のコマンドでPipelineを実行できます:\n")
    print(
        "python scripts/jquants_lab_pipeline.py --source local "
        f"--local-snapshot-dir {output_dir} --codes {' '.join(codes)} "
        f"--start {start.isoformat()} --end {end.isoformat()}"
    )


def _codes_at(adapter: JQuantsAdapter, as_of: date) -> set[str]:
    """指定as_ofでのMasterから、内部Codeへ正規化できた銘柄Codeの集合を返す。

    正規化に失敗した行(普通株以外の可能性)はこの診断の対象外として単に除く
    (equities_master_payload_to_listing_recordsと同じ非厳格な扱い、D0036)。
    """
    try:
        master_result = adapter.fetch_equities_master(as_of=as_of)
    except DataSourceError as exc:
        raise SystemExit(f"銘柄マスタ(as_of={as_of.isoformat()})取得に失敗しました: {exc}") from exc
    codes: set[str] = set()
    for row in master_result.payload:
        provider_code = str(row["Code"])
        try:
            codes.add(normalize_provider_code_to_internal(provider_code))
        except TickerCodeNormalizationError:
            continue
    return codes


def run_master_pit_check(*, date_before: date, date_after: date, code: str) -> None:
    """`/v2/equities/master`のdateパラメータが真のPoint-in-Time Snapshotかどうかを診断する。

    出力先ディレクトリへは何も保存しない(LocalSnapshotAdapter用のSnapshotを汚さない、
    診断専用モード)。判定結果自体は目視確認用であり、このスクリプトが自動で
    `resolution`等を書き換えることはしない(DECISIONS.md D0038参照)。
    """
    load_dotenv()
    adapter = JQuantsAdapter()
    if not adapter.configured:
        raise SystemExit(
            "JQUANTS_API_KEY が設定されていません。リポジトリルートの.envに設定してください"
            "(絶対にリポジトリへコミットしないこと)。"
        )

    print(f"銘柄マスタ(as_of={date_before.isoformat()})取得")
    codes_before = _codes_at(adapter, date_before)
    print(f"  -> {len(codes_before)}件(正規化済み)")

    print(f"銘柄マスタ(as_of={date_after.isoformat()})取得")
    codes_after = _codes_at(adapter, date_after)
    print(f"  -> {len(codes_after)}件(正規化済み)")

    in_before = code in codes_before
    in_after = code in codes_after
    print(f"\ncode={code}: as_of={date_before.isoformat()}時点で{'含まれる' if in_before else '含まれない'}")
    print(f"code={code}: as_of={date_after.isoformat()}時点で{'含まれる' if in_after else '含まれない'}")

    if in_before and not in_after:
        print(
            "\n判定: dateパラメータの前後でこのCodeの有無が変化した -> "
            "真のPoint-in-Time Snapshotである可能性が高い(ただし1銘柄・1API呼び出しのみでの"
            "確認のため、DECISIONS.md D0038へ結果を追記し、他銘柄でも再現するか確認することを推奨)。"
        )
    elif in_before and in_after:
        print(
            "\n判定: 両方のas_ofで含まれたままだった -> このCodeでは廃止日をまたげていない"
            "(日付の選び方が不適切な可能性がある)か、Masterが常に「現在の状態」しか"
            "返していない可能性がある。廃止日をより確実に挟む日付、または別のCodeで再確認すること。"
        )
    else:
        print(
            "\n判定: 想定外の組み合わせ(前後どちらでも含まれない、または前で含まれず後で含まれる)。"
            "指定したdate_before/date_after/codeの組み合わせを見直すこと。"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codes", nargs="+", default=["7203", "6758", "8056", "3626"])
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_LAB_DIR / "01_data" / "raw" / "local_snapshot_input",
    )
    parser.add_argument(
        "--master-pit-check",
        nargs=2,
        metavar=("DATE_BEFORE", "DATE_AFTER"),
        type=date.fromisoformat,
        default=None,
        help="通常のSnapshot取得は行わず、指定した2つの日付でMasterのPoint-in-Time性を診断する。",
    )
    parser.add_argument(
        "--master-pit-check-code",
        default=None,
        help="--master-pit-check使用時の対象内部Code(4桁)。過去に上場廃止された銘柄を指定すること。",
    )
    args = parser.parse_args()

    if args.master_pit_check is not None:
        if args.master_pit_check_code is None:
            raise SystemExit("--master-pit-check使用時は --master-pit-check-code の指定が必須です。")
        date_before, date_after = args.master_pit_check
        run_master_pit_check(date_before=date_before, date_after=date_after, code=args.master_pit_check_code)
        return

    if args.start is None or args.end is None:
        raise SystemExit("--start と --end の指定が必須です(--master-pit-check使用時を除く)。")
    fetch_all(
        codes=args.codes,
        start=args.start,
        end=args.end,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
