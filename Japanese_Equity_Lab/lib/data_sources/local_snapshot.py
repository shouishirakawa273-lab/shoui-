"""ユーザーがローカル環境で取得したJ-Quants API V2の生レスポンスを読み込む DataSourceAdapter。

このセッションはネットワークポリシーによりJ-Quants等の外部APIへ疎通できない
(api.jquants.com/jpx.gitbook.io(ドキュメント)/Yahoo Finance/example.com いずれも
拒否されることを確認済み)。そのため、ユーザーがネットワーク接続可能な別環境
(ローカルPC等)で取得したJ-Quants V2の生レスポンス(JSON、日次BarのみCSVも可)を
ファイルとして受け取り、Snapshot保存・変換・Backtest実行以降をこの環境で行うための
Adapter。

**ディレクトリ内のファイル命名規約**(このAdapterが読みに行くファイル名):

    equity_bars_<code>.json    /v2/equities/bars/daily の生レスポンス(1銘柄分)
    equity_bars_<code>.csv     (JSONが用意できない場合の代替。列: Code,Date,O,H,L,C,Vo,
                                 AdjFactor,ExRT。J-Quantsの実列名と異なる場合は
                                 事前にリネームすること)
    trading_calendar.json      /v2/markets/calendar の生レスポンス
    topix_bars.json            /v2/indices/bars/daily/topix の生レスポンス
    general_index_bars_<code>.json  /v2/indices/bars/daily の生レスポンス(使う場合のみ)
    equities_master.json       /v2/equities/master の生レスポンス

JSONファイルは、J-Quantsが返す生のレスポンス全体(``{"data": [...], "pagination_key":
null}`` 等のトップレベルキー付き)をそのまま保存したものを想定する(加工しないこと。
複数ページに分かれていた場合は、``data``配列を1つに結合してから保存すること
-- ``scripts/fetch_jquants_local_snapshot.py``を使えば自動的に結合される)。

retrieved_atは、呼び出し側が明示的に指定しない限りファイルの最終更新時刻(mtime)を
近似値として使う。正確な取得日時が必要な場合はコンストラクタで明示的に指定すること
(mtimeはコピー等で書き換わりうるため、あくまで近似値であることに注意)。
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from lib.data_sources.base import LIGHT_PLAN_ASSUMED, DataSourceCapabilities, RawFetchResult
from lib.errors import DataSourceError

RESPONSE_SCHEMA_VERSION = "jquants-v2(local, 未検証)"
_DATA_KEY = "data"


class LocalSnapshotAdapter:
    """ローカル環境で取得済みのJ-Quants V2生レスポンスファイルを読み込むAdapter。"""

    def __init__(self, snapshot_dir: Path, *, retrieved_at: datetime | None = None) -> None:
        if not snapshot_dir.exists():
            raise DataSourceError(f"snapshot_dirが存在しません: {snapshot_dir}")
        self._dir = snapshot_dir
        self._retrieved_at_override = retrieved_at

    @property
    def capabilities(self) -> DataSourceCapabilities:
        return LIGHT_PLAN_ASSUMED

    def _retrieved_at_for(self, path: Path) -> datetime:
        if self._retrieved_at_override is not None:
            return self._retrieved_at_override
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    def _find_file(self, stem: str) -> Path | None:
        for suffix in (".json", ".csv"):
            candidate = self._dir / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
        return None

    def _read_json_data(self, path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        records = data.get(_DATA_KEY)
        if records is None:
            raise DataSourceError(
                f"{path} に '{_DATA_KEY}' キーが見つかりません(J-Quants V2の生レスポンス"
                '``{"data": [...]}``をそのまま保存してください)'
            )
        return list(records)

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def _read_rows(self, path: Path) -> list[dict[str, Any]]:
        if path.suffix == ".csv":
            return self._read_csv(path)
        return self._read_json_data(path)

    def fetch_equity_bars(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        records: list[dict[str, Any]] = []
        latest_path: Path | None = None
        missing: list[str] = []
        for code in codes:
            path = self._find_file(f"equity_bars_{code}")
            if path is None:
                missing.append(code)
                continue
            latest_path = path
            rows = self._read_rows(path)
            records.extend(row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date)
        if missing:
            raise DataSourceError(
                f"以下の銘柄のequity_barsファイルが見つかりません: {missing}。"
                f"{self._dir} に equity_bars_<code>.json (または .csv) を配置してください。"
            )
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/equities/bars/daily",
            request_parameters={"codes": list(codes), "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(latest_path) if latest_path else datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        path = self._find_file("trading_calendar")
        if path is None:
            raise DataSourceError(f"{self._dir} に trading_calendar.json が見つかりません。")
        rows = self._read_rows(path)
        records = [row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date]
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/markets/calendar",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(path),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult:
        path = self._find_file("topix_bars")
        if path is None:
            raise DataSourceError(f"{self._dir} に topix_bars.json が見つかりません。")
        rows = self._read_rows(path)
        records = [row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date]
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/indices/bars/daily/topix",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(path),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_general_index_bars(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        path = self._find_file(f"general_index_bars_{index_code}")
        if path is None:
            raise DataSourceError(f"{self._dir} に general_index_bars_{index_code}.json が見つかりません。")
        rows = self._read_rows(path)
        records = [row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date]
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/indices/bars/daily",
            request_parameters={"code": index_code, "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(path),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_equities_master(self, *, as_of: date | None = None) -> RawFetchResult:
        path = self._find_file("equities_master")
        if path is None:
            raise DataSourceError(f"{self._dir} に equities_master.json が見つかりません。")
        records = self._read_rows(path)
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/equities/master",
            request_parameters={"as_of": as_of.isoformat() if as_of else None},
            retrieved_at=self._retrieved_at_for(path),
            data_period=(as_of.isoformat() if as_of else "current"),
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_financial_statements(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        """`financial_summary_<code>.json`(または`.csv`)を読み込む(Phase4A、D0043)。
        各行は`DiscDate`で期間フィルタする(equity_barsの`Date`とは異なるField名)。
        """
        records: list[dict[str, Any]] = []
        latest_path: Path | None = None
        missing: list[str] = []
        for code in codes:
            path = self._find_file(f"financial_summary_{code}")
            if path is None:
                missing.append(code)
                continue
            latest_path = path
            rows = self._read_rows(path)
            records.extend(row for row in rows if start_date <= date.fromisoformat(str(row["DiscDate"])) <= end_date)
        if missing:
            raise DataSourceError(
                f"以下の銘柄のfinancial_summaryファイルが見つかりません: {missing}。"
                f"{self._dir} に financial_summary_<code>.json (または .csv) を配置してください。"
            )
        return RawFetchResult(
            source="jquants_local",
            endpoint="/v2/fins/summary",
            request_parameters={"codes": list(codes), "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(latest_path) if latest_path else datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )
