"""ユーザーがローカル環境で取得したJ-Quantsの生レスポンスを読み込む DataSourceAdapter。

このセッションはネットワークポリシーによりJ-Quants等の外部APIへ疎通できない
(api.jquants.com/Yahoo Finance/example.com いずれも403で拒否されることを確認済み)。
そのため、ユーザーがネットワーク接続可能な別環境(ローカルPC等)で取得した
J-Quantsの生レスポンス(JSON、日次株価のみCSVも可)をファイルとして受け取り、
Snapshot保存・変換・Backtest実行以降をこの環境で行うためのAdapter。

**ディレクトリ内のファイル命名規約**(このAdapterが読みに行くファイル名):

    daily_quotes_<code>.json   /prices/daily_quotes の生レスポンス(1銘柄分)
    daily_quotes_<code>.csv    (JSONが用意できない場合の代替。列: Code,Date,Open,High,
                                 Low,Close,Volume。J-Quantsの実列名と異なる場合は
                                 事前にリネームすること)
    trading_calendar.json      /markets/trading_calendar の生レスポンス
    indices_<index_code>.json  /indices の生レスポンス(TOPIXの場合 index_code="0000" を
                                 想定しているが未検証。実際のコードに合わせてファイル名を
                                 決めること)
    listed_info.json           /listed/info の生レスポンス

JSONファイルは、J-Quantsが返す生のレスポンス全体(``{"daily_quotes": [...]}`` 等の
トップレベルキー付き)をそのまま保存したものを想定する(加工しないこと)。

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

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

RESPONSE_SCHEMA_VERSION = "jquants-v1(local, 未検証)"


class LocalSnapshotAdapter:
    """ローカル環境で取得済みのJ-Quants生レスポンスファイルを読み込むAdapter。"""

    def __init__(self, snapshot_dir: Path, *, retrieved_at: datetime | None = None) -> None:
        if not snapshot_dir.exists():
            raise DataSourceError(f"snapshot_dirが存在しません: {snapshot_dir}")
        self._dir = snapshot_dir
        self._retrieved_at_override = retrieved_at

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

    def _read_json_key(self, path: Path, key: str) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        records = data.get(key)
        if records is None:
            raise DataSourceError(f"{path} に '{key}' キーが見つかりません(J-Quantsの生レスポンスをそのまま保存してください)")
        return list(records)

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def _read_rows(self, path: Path, *, json_key: str) -> list[dict[str, Any]]:
        if path.suffix == ".csv":
            return self._read_csv(path)
        return self._read_json_key(path, json_key)

    def fetch_daily_quotes(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        records: list[dict[str, Any]] = []
        latest_path: Path | None = None
        missing: list[str] = []
        for code in codes:
            path = self._find_file(f"daily_quotes_{code}")
            if path is None:
                missing.append(code)
                continue
            latest_path = path
            rows = self._read_rows(path, json_key="daily_quotes")
            records.extend(row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date)
        if missing:
            raise DataSourceError(
                f"以下の銘柄のdaily_quotesファイルが見つかりません: {missing}。"
                f"{self._dir} に daily_quotes_<code>.json (または .csv) を配置してください。"
            )
        return RawFetchResult(
            source="jquants_local",
            endpoint="/prices/daily_quotes",
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
        rows = self._read_rows(path, json_key="trading_calendar")
        records = [row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date]
        return RawFetchResult(
            source="jquants_local",
            endpoint="/markets/trading_calendar",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(path),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_index_prices(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        path = self._find_file(f"indices_{index_code}")
        if path is None:
            raise DataSourceError(f"{self._dir} に indices_{index_code}.json が見つかりません。")
        rows = self._read_rows(path, json_key="indices")
        records = [row for row in rows if start_date <= date.fromisoformat(str(row["Date"])) <= end_date]
        return RawFetchResult(
            source="jquants_local",
            endpoint="/indices",
            request_parameters={"code": index_code, "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=self._retrieved_at_for(path),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_listed_info(self, *, as_of: date | None = None) -> RawFetchResult:
        path = self._find_file("listed_info")
        if path is None:
            raise DataSourceError(f"{self._dir} に listed_info.json が見つかりません。")
        records = self._read_rows(path, json_key="info")
        return RawFetchResult(
            source="jquants_local",
            endpoint="/listed/info",
            request_parameters={"as_of": as_of.isoformat() if as_of else None},
            retrieved_at=self._retrieved_at_for(path),
            data_period=(as_of.isoformat() if as_of else "current"),
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )
